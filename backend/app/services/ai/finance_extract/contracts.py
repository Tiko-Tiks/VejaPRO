"""Finance extract scope contracts — V2.3 proposal-only extraction."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AIFinanceExtractResult(BaseModel):
    """Structured output from financial document extraction.

    This is a **proposal** only — the system MUST NOT auto-confirm payments
    based on AI output. An admin reviews and confirms manually.
    """

    vendor_name: str = ""
    amount: float = 0.0
    currency: str = "EUR"
    date: str = ""
    description: str = ""
    confidence: float = 0.0
    model_version: str = ""
    raw_extraction: dict[str, Any] = {}
