"""Mock provider — deterministic responses for tests and fallback."""

from __future__ import annotations

import time

from .base import BaseProvider, ProviderResult


class MockProvider(BaseProvider):
    name = "mock"

    async def generate(
        self,
        prompt: str,
        *,
        model: str = "",
        temperature: float = 0.3,
        max_tokens: int = 1024,
        timeout_seconds: float = 8.0,
    ) -> ProviderResult:
        t0 = time.monotonic()
        text = '{"intent": "mock", "confidence": 1.0, "params": {}}'
        elapsed = (time.monotonic() - t0) * 1000
        return ProviderResult(
            raw_text=text,
            model=model or "mock-v1",
            provider=self.name,
            prompt_tokens=len(prompt.split()),
            completion_tokens=len(text.split()),
            latency_ms=round(elapsed, 2),
        )
