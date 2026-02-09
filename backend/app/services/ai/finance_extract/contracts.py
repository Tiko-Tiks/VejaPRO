"""Finance extract scope contracts — placeholder for Phase 2."""

from __future__ import annotations

from pydantic import BaseModel


class AIFinanceExtractResult(BaseModel):
    """Structured output from financial document extraction (placeholder)."""

    vendor_name: str = ""
    amount: float = 0.0
    currency: str = "EUR"
    date: str = ""
    description: str = ""
    confidence: float = 0.0
