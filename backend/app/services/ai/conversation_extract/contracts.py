"""Conversation extract scope contracts — structured client data extraction."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_validator


class ExtractedField(BaseModel):
    """A single extracted field with value and confidence."""

    value: str = ""
    confidence: float = 0.0

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            msg = f"Confidence must be 0.0-1.0, got {v}"
            raise ValueError(msg)
        return round(v, 2)


_SUGGESTION_FIELDS = (
    "client_name",
    "phone",
    "email",
    "address",
    "service_type",
    "urgency",
    "area_m2",
)


class AIConversationExtractResult(BaseModel):
    """Structured output from conversation/transcript extraction."""

    client_name: ExtractedField = ExtractedField()
    phone: ExtractedField = ExtractedField()
    email: ExtractedField = ExtractedField()
    address: ExtractedField = ExtractedField()
    service_type: ExtractedField = ExtractedField()
    urgency: ExtractedField = ExtractedField()
    area_m2: ExtractedField = ExtractedField()
    model_version: str = ""
    raw_extraction: dict[str, Any] = {}

    def to_suggestions_dict(self) -> dict[str, dict[str, Any]]:
        """Convert to the format expected by ``merge_ai_suggestions()``."""
        result: dict[str, dict[str, Any]] = {}
        for field_name in _SUGGESTION_FIELDS:
            field: ExtractedField = getattr(self, field_name)
            if field.value:
                result[field_name] = {
                    "value": field.value,
                    "confidence": field.confidence,
                }
        return result
