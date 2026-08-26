"""Agent Runtime — the agentic loop with session history & multi-turn memory.

Includes a deterministic fallback: if the user clearly requested to buy/order
and the LLM failed to call create_order, the runtime executes it directly.
This guarantees purchase intent always reaches the policy engine.
"""

import json
import logging
import time
import uuid
import re
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AgentSession
from app.llm.base import LLMProvider, Message, create_llm_provider
from app.agent.tools import TOOL_SCHEMAS, execute_tool
from app.audit.logger import log_agent_action, log_event

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are RazorBuy, an AI commerce assistant for an online electronics store.

Your job is to help users discover products, compare options, negotiate prices within merchant limits, and place orders.

CRITICAL INSTRUCTIONS:
1. ALWAYS use tools to get product information. NEVER fabricate prices, inventory, or product details.
2. When a user asks to buy or order a product (e.g. "buy P101", "order 2 SoundMax", "buy it"):
   a. First check `get_current_price`.
   b. If a discount was requested, call `calculate_offer`.
   c. Immediately call `create_order` with the product_id, quantity (default to 1 if unstated), and discount_amount.
3. NEVER say "Your order has been placed" unless you have actually called `create_order` and received a successful response.
4. If `create_order` returns order_status "APPROVED", tell the user their order is placed and approved.
5. If it returns "BLOCKED" or "AWAITING_CONFIRMATION", explain the exact reason codes to the user clearly.
6. Be concise, direct, helpful, and polite. Currency is INR.

AVAILABLE CATEGORIES: wireless_earbuds, headphones, speakers, smartwatches, accessories
"""

BUY_KEYWORDS = ["buy", "order", "purchase", "place order", "checkout", "get me", "take one", "order it"]


class AgentRuntime:
    """Manages the agent loop with step limits, multi-turn session state, and audit trails."""

    def __init__(
        self,
        db: AsyncSession,
        merchant_id: str,
        user_id: str,
        max_steps: int = 15,
    ):
        self.db = db
        self.merchant_id = merchant_id
        self.user_id = user_id
        self.max_steps = max_steps
        self.llm: LLMProvider = create_llm_provider()
        self.steps: list[dict] = []

    async def run(self, user_message: str, session_id: str | None = None) -> dict:
        """Run the agent loop with session history loading and saving."""
        session_uuid = uuid.UUID(session_id) if session_id else uuid.uuid4()
        actual_session_id = str(session_uuid)

        # 1. Fetch or create AgentSession for multi-turn history
        stmt = select(AgentSession).where(AgentSession.id == session_uuid)
        res = await self.db.execute(stmt)
        agent_session = res.scalar_one_or_none()

        if not agent_session:
            agent_session = AgentSession(
                id=session_uuid,
                user_id=uuid.UUID(self.user_id),
                merchant_id=uuid.UUID(self.merchant_id),
                conversation_history=[],
            )
            self.db.add(agent_session)
            await self.db.flush()

        # 2. Reconstruct messages from history
        history = agent_session.conversation_history or []
        messages = [Message(role="system", content=SYSTEM_PROMPT)]

        for h in history:
            messages.append(
                Message(
                    role=h.get("role", "user"),
                    content=h.get("content", ""),
                    tool_calls=h.get("tool_calls"),
                    name=h.get("name"),
                )
            )

        # Append new user message
        messages.append(Message(role="user", content=user_message))

        await log_event(
            db=self.db,
            actor="agent",
            action="AGENT_SESSION_START",
            status="SUCCESS",
            session_id=actual_session_id,
            input_data={"user_message": user_message[:200]},
            result="STARTED",
        )

        step_count = 0
        final_response = ""
        tools_executed: list[str] = []
        last_product_id: Optional[str] = None
        last_quantity = 1
        last_discount = 0.0

        while step_count < self.max_steps:
            step_count += 1
            step_start = time.time()

            try:
                llm_response = await self.llm.chat(
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    temperature=0.1,
                )

                if not llm_response.has_tool_calls:
                    final_response = llm_response.content
                    messages.append(Message(role="assistant", content=final_response))
                    self.steps.append({
                        "step": step_count,
                        "type": "response",
                        "content": final_response[:500],
                        "latency_ms": int((time.time() - step_start) * 1000),
                    })
                    break

                # Assistant message with tool calls
                assistant_msg = Message(
                    role="assistant",
                    content=llm_response.content or "",
                    tool_calls=[
                        {
                            "function": {
                                "name": tc.name,
                                "arguments": tc.arguments if isinstance(tc.arguments, dict) else {},
                            },
                        }
                        for tc in llm_response.tool_calls
                    ],
                )
                messages.append(assistant_msg)

                # Execute tool calls
                for tc in llm_response.tool_calls:
                    tool_start = time.time()

                    # Track last product / quantity / discount
                    if tc.name in ("get_product", "get_current_price", "check_inventory"):
                        pid = tc.arguments.get("product_id")
                        if pid:
                            last_product_id = pid
                    if tc.name == "create_order":
                        pid = tc.arguments.get("product_id")
                        if pid:
                            last_product_id = pid
                        last_quantity = tc.arguments.get("quantity", 1)
                        last_discount = tc.arguments.get("discount_amount", 0.0)

                    result = await execute_tool(
                        tool_name=tc.name,
                        arguments=tc.arguments,
                        db=self.db,
                        merchant_id=self.merchant_id,
                        user_id=self.user_id,
                        session_id=actual_session_id,
                    )

                    tool_latency = int((time.time() - tool_start) * 1000)

                    await log_agent_action(
                        db=self.db,
                        session_id=actual_session_id,
                        tool_name=tc.name,
                        arguments=tc.arguments,
                        result_data=result,
                        status=result.get("status", "UNKNOWN"),
                        latency_ms=tool_latency,
                    )

                    self.steps.append({
                        "step": step_count,
                        "type": "tool_call",
                        "tool": tc.name,
                        "arguments": tc.arguments,
                        "result_summary": _summarize_result(result),
                        "status": result.get("status", "UNKNOWN"),
                        "latency_ms": tool_latency,
                    })

                    tools_executed.append(tc.name)

                    # Feed tool result back into history
                    messages.append(
                        Message(
                            role="tool",
                            content=json.dumps(result, default=str),
                            name=tc.name,
                        )
                    )

            except Exception as e:
                logger.error(f"Agent step {step_count} error: {e}", exc_info=True)
                final_response = "I encountered an error processing your request."
                self.steps.append({
                    "step": step_count,
                    "type": "error",
                    "error": str(e),
                })
                break
        else:
            final_response = "I have reached the maximum reasoning steps for this request."
            await log_event(
                db=self.db,
                actor="agent",
                action="AGENT_LOOP_DETECTED",
                status="BLOCKED",
                session_id=actual_session_id,
                reason_codes=["STEP_LIMIT_REACHED"],
                result="TERMINATED",
            )

        # ── DETERMINISTIC PURCHASE FALLBACK ──
        # If the user explicitly requested to buy and no successful create_order happened,
        # we place the order automatically using the last product mentioned.
        created_order_result = None
        for s in self.steps:
            if s.get("type") == "tool_call" and s.get("tool") == "create_order" and s.get("status") == "SUCCESS":
                created_order_result = s
                break

        if not created_order_result and last_product_id and _is_buy_request(user_message):
            logger.info("LLM failed to call create_order. Executing deterministic fallback.")
            fallback_start = time.time()
            fallback_args = {
                "product_id": last_product_id,
                "quantity": last_quantity,
                "discount_amount": last_discount,
            }
            result = await execute_tool(
                tool_name="create_order",
                arguments=fallback_args,
                db=self.db,
                merchant_id=self.merchant_id,
                user_id=self.user_id,
                session_id=actual_session_id,
            )
            fallback_latency = int((time.time() - fallback_start) * 1000)

            await log_agent_action(
                db=self.db,
                session_id=actual_session_id,
                tool_name="create_order",
                arguments=fallback_args,
                result_data=result,
                status=result.get("status", "UNKNOWN"),
                latency_ms=fallback_latency,
            )

            self.steps.append({
                "step": step_count + 1,
                "type": "tool_call",
                "tool": "create_order",
                "arguments": fallback_args,
                "result_summary": _summarize_result(result),
                "status": result.get("status", "UNKNOWN"),
                "latency_ms": fallback_latency,
            })

            if result.get("status") == "SUCCESS":
                order_status = result.get("order_status", "APPROVED")
                if order_status == "APPROVED":
                    final_response = (
                        f"Your order has been placed and approved! Total: ₹{result.get('total')} "
                        f"({result.get('currency')}). You can now pay in the Orders tab."
                    )
                else:
                    final_response = (
                        f"Your order is pending confirmation. Total: ₹{result.get('total')} "
                        f"({result.get('currency')}). Please confirm it to proceed."
                    )
            elif result.get("status") == "BLOCKED":
                reasons = result.get("reason_codes", [])
                final_response = (
                    f"I could not place the order. Policy blocked it for: {', '.join(reasons)}. "
                    f"No money was moved."
                )
            else:
                final_response = f"Order creation failed: {result.get('error', 'unknown')}"

        # Save session history back to DB (excluding system prompt)
        saved_history = [
            m.to_dict() for m in messages if m.role != "system"
        ]
        agent_session.conversation_history = saved_history

        await log_event(
            db=self.db,
            actor="agent",
            action="AGENT_SESSION_END",
            status="SUCCESS",
            session_id=actual_session_id,
            result="COMPLETED",
            metadata={"total_steps": step_count},
        )

        await self.db.commit()

        return {
            "session_id": actual_session_id,
            "response": final_response,
            "steps": self.steps,
            "status": "completed" if step_count < self.max_steps else "step_limit",
            "total_steps": step_count + (1 if not created_order_result and last_product_id and _is_buy_request(user_message) else 0),
        }


def _is_buy_request(message: str) -> bool:
    """Detect if the user's message clearly requests a purchase."""
    msg = message.lower().strip()
    return any(kw in msg for kw in BUY_KEYWORDS)


def _summarize_result(result: dict) -> str:
    status = result.get("status", "UNKNOWN")
    if status == "SUCCESS":
        if "total_found" in result:
            return f"Found {result['total_found']} products"
        if "order_id" in result:
            return f"Order created ({result.get('order_status', 'APPROVED')})"
        if "price" in result:
            return f"Price: ₹{result['price']}"
        if "available" in result:
            return f"Available: {result['available']}"
        if "final_price" in result:
            return f"Final price: ₹{result['final_price']}"
        return "Success"
    elif status == "BLOCKED":
        reasons = result.get("reason_codes", [])
        return f"Blocked: {', '.join(reasons)}"
    else:
        return f"Error: {result.get('error', 'unknown')[:100]}"