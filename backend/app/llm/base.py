"""LLM Provider abstraction — model-agnostic interface."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    total_tokens: int = 0

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


@dataclass
class Message:
    role: str
    content: str = ""
    tool_calls: Optional[list[dict]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"role": self.role, "content": self.content or ""}
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.name:
            d["name"] = self.name
        return d


class LLMProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...


def create_llm_provider() -> LLMProvider:
    from app.config.settings import get_settings
    settings = get_settings()

    if settings.llm_provider == "local":
        from app.llm.local import OllamaProvider
        return OllamaProvider(
            base_url=settings.local_llm_base_url,
            model=settings.local_llm_model,
        )
    elif settings.llm_provider == "hosted":
        from app.llm.hosted import HostedProvider
        return HostedProvider(
            api_key=settings.hosted_llm_api_key,
            model=settings.hosted_llm_model,
        )
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")