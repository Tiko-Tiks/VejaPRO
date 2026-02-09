"""Intent scope contracts — AIIntentResult + validation."""

from __future__ import annotations

from pydantic import BaseModel, field_validator

VALID_INTENTS = frozenset(
    {
        "schedule_visit",
        "request_quote",
        "check_status",
        "complaint",
        "general_inquiry",
        "cancel",
        "reschedule",
        "mock",
    }
)


class AIIntentResult(BaseModel):
    """Structured output expected from intent classification."""

    intent: str
    confidence: float
    params: dict = {}

    @field_validator("intent")
    @classmethod
    def intent_must_be_known(cls, v: str) -> str:
        if v not in VALID_INTENTS:
            msg = f"Unknown intent {v!r}; valid: {sorted(VALID_INTENTS)}"
            raise ValueError(msg)
        return v

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            msg = f"Confidence must be 0.0–1.0, got {v}"
            raise ValueError(msg)
        return v
