"""Contracts for AI Email Sentiment Classification."""

from __future__ import annotations

from dataclasses import dataclass, field

VALID_LABELS = {"NEGATIVE", "NEUTRAL", "POSITIVE"}

VALID_REASON_CODES = {
    "DELAY",
    "QUALITY",
    "PRICING",
    "RUDENESS",
    "FRUSTRATION",
    "THREAT",
    "OTHER",
}

MAX_REASON_CODES = 5


@dataclass
class SentimentResult:
    """Immutable sentiment classification result."""

    label: str  # NEGATIVE | NEUTRAL | POSITIVE
    confidence: float  # 0.0–1.0
    reason_codes: list[str] = field(default_factory=list)
