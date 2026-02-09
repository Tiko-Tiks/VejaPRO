"""Abstract base for all AI providers."""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderResult:
    """Immutable result returned by every provider."""

    raw_text: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0


class BaseProvider(abc.ABC):
    """Contract that every AI provider must implement."""

    name: str = "base"

    @abc.abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        model: str = "",
        temperature: float = 0.3,
        max_tokens: int = 1024,
        timeout_seconds: float = 8.0,
    ) -> ProviderResult:
        """Send *prompt* and return a ``ProviderResult``."""
