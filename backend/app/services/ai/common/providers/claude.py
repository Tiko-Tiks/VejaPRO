"""Anthropic / Claude provider."""

from __future__ import annotations

import logging
import time

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)


class ClaudeProvider(BaseProvider):
    name = "claude"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def generate(
        self,
        prompt: str,
        *,
        model: str = "",
        temperature: float = 0.3,
        max_tokens: int = 1024,
        timeout_seconds: float = 8.0,
    ) -> ProviderResult:
        import httpx

        model = model or "claude-3-5-haiku-20241022"
        t0 = time.monotonic()

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()

        elapsed = (time.monotonic() - t0) * 1000
        text = data["content"][0]["text"]
        usage = data.get("usage", {})

        return ProviderResult(
            raw_text=text,
            model=model,
            provider=self.name,
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            latency_ms=round(elapsed, 2),
        )
