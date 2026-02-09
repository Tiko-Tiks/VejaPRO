"""Groq provider (OpenAI-compatible API)."""

from __future__ import annotations

import logging
import time

from .base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)


class GroqProvider(BaseProvider):
    name = "groq"

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

        model = model or "llama-3.1-70b"
        t0 = time.monotonic()

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
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
        choice = data["choices"][0]
        text = choice["message"]["content"]
        usage = data.get("usage", {})

        return ProviderResult(
            raw_text=text,
            model=model,
            provider=self.name,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            latency_ms=round(elapsed, 2),
        )
