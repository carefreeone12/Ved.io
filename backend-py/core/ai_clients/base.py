"""
Abstract AI client protocol and common types.
Maps to Go pkg/ai/client.go.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Protocol that all LLM clients must satisfy."""

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> str:
        ...

    async def test_connection(self) -> bool:
        ...
