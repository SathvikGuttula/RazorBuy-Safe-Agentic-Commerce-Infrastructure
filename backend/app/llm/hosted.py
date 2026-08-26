"""Hosted LLM Provider — OpenAI-compatible API (Groq, OpenAI, etc.).

Uses the same /v1/chat/completions format.
Set HOSTED_LLM_API_KEY and HOSTED_LLM_MODEL in .env.
"""

import json
import logging

import httpx

from app.llm.base import LLMProvider, LLMResponse, Message, ToolCall

logger = logging.getLogger(__name__)


class HostedProvider(LLMProvider):
    """Hosted LLM via OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "llama-3.1-70b-versatile",
        base_url: str = "https://api.groq.com/openai/v1",
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    @property
    def provider_name(self) -> str:
        return f"hosted:{self.model}"

    def is_available(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("your_"))

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        if not self.is_available():
            return LLMResponse(
                content="Hosted LLM not configured. Set HOSTED_LLM_API_KEY in .env",
                model=self.model,
            )

        payload: dict = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

            choice = data["choices"][0]
            message = choice["message"]
            content = message.get("content", "") or ""
            raw_tool_calls = message.get("tool_calls", [])

            tool_calls = []
            for tc in raw_tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args_str = fn.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except json.JSONDecodeError:
                    args = {}
                if name:
                    tool_calls.append(ToolCall(name=name, arguments=args))

            usage = data.get("usage", {})
            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                model=self.model,
                total_tokens=usage.get("total_tokens", 0),
            )

        except Exception as e:
            logger.error(f"Hosted LLM error: {e}")
            return LLMResponse(
                content=f"Hosted LLM error: {e}",
                model=self.model,
            )