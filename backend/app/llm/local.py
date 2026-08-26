"""Ollama LLM Provider — local model inference with tool calling."""

import json
import logging
import uuid

import httpx

from app.llm.base import LLMProvider, LLMResponse, Message, ToolCall

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Local LLM via Ollama REST API. Supports native tool calling."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen2.5:7b"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    @property
    def provider_name(self) -> str:
        return f"ollama:{self.model}"

    def is_available(self) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Call Ollama /api/chat with tool support."""
        payload: dict = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if tools:
            payload["tools"] = tools

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            message = data.get("message", {})
            content = message.get("content", "") or ""
            raw_tool_calls = message.get("tool_calls", [])

            tool_calls = []
            for tc in raw_tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                if name:
                    tool_calls.append(ToolCall(name=name, arguments=args))

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                model=self.model,
                total_tokens=data.get("eval_count", 0) + data.get("prompt_eval_count", 0),
            )

        except httpx.TimeoutException:
            logger.error("Ollama request timed out")
            return LLMResponse(
                content="I'm sorry, the AI model took too long to respond. Please try again.",
                model=self.model,
            )
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return LLMResponse(
                content=f"I encountered an error communicating with the AI model: {e}",
                model=self.model,
            )