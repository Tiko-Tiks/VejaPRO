"""Vision scope contracts — placeholder for Phase 2."""

from __future__ import annotations

from pydantic import BaseModel


class AIVisionResult(BaseModel):
    """Structured output from vision analysis (placeholder)."""

    description: str = ""
    labels: list[str] = []
    confidence: float = 0.0
