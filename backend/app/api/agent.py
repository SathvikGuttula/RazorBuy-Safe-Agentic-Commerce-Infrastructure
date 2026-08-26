"""Agent API — chat endpoint with prompt-injection detection."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.database.models import Merchant, User
from app.agent.runtime import AgentRuntime
from app.security.validation import scan_text_for_injection
from app.audit.logger import log_event

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    merchant_id: Optional[str] = None


class StepInfo(BaseModel):
    step: int
    type: str
    tool: Optional[str] = None
    arguments: Optional[dict] = None
    result_summary: Optional[str] = None
    status: Optional[str] = None
    latency_ms: Optional[int] = None
    content: Optional[str] = None
    error: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    response: str
    steps: list[StepInfo]
    status: str
    total_steps: int
    warnings: list[str] = []


@router.post("/agent/chat", response_model=ChatResponse)
async def agent_chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    merchant_id, user_id = request.merchant_id, request.user_id

    if not merchant_id:
        m = (await db.execute(select(Merchant).limit(1))).scalar_one_or_none()
        if not m:
            raise HTTPException(404, "No merchant found. Run seed_db.py")
        merchant_id = str(m.id)
    if not user_id:
        u = (await db.execute(select(User).limit(1))).scalar_one_or_none()
        if not u:
            raise HTTPException(404, "No user found. Run seed_db.py")
        user_id = str(u.id)

    # ── Prompt injection scan (detection layer; policy is the real defense) ──
    warnings: list[str] = []
    scan = scan_text_for_injection(request.message)
    if scan.is_suspicious:
        await log_event(
            db=db, actor="system", action="PROMPT_INJECTION_DETECTED",
            status="ESCALATED", session_id=request.session_id,
            resource_type="message", resource_id=None,
            input_data={"message_preview": request.message[:200]},
            result="FLAGGED",
            reason_codes=["PROMPT_INJECTION_DETECTED"],
            metadata={"matched_count": len(scan.matched_patterns)},
        )
        await db.commit()
        warnings.append(
            "Potentially manipulative instruction detected. "
            "Financial policy remains authoritative and cannot be overridden."
        )

    runtime = AgentRuntime(
        db=db, merchant_id=merchant_id, user_id=user_id, max_steps=15
    )
    result = await runtime.run(
        user_message=request.message, session_id=request.session_id
    )

    return ChatResponse(
        session_id=result["session_id"],
        response=result["response"],
        steps=[StepInfo(**s) for s in result["steps"]],
        status=result["status"],
        total_steps=result["total_steps"],
        warnings=warnings,
    )