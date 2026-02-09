"""Finance document extraction service — V2.3 proposal-only AI extraction.

IMPORTANT: This service produces *proposals* only. It MUST NOT auto-confirm
any payments. The extracted data is stored in payments.ai_extracted_data
for admin review.
"""

from __future__ import annotations

import logging

from app.services.ai.common.json_tools import extract_json
from app.services.ai.common.router import resolve
from app.services.ai.finance_extract.contracts import AIFinanceExtractResult

logger = logging.getLogger(__name__)

FINANCE_EXTRACT_PROMPT = """Analyze this financial document and extract structured data.

Return a JSON object with these fields:
- vendor_name: the company/person name on the document
- amount: the total amount as a number (e.g. 123.45)
- currency: 3-letter currency code (default EUR)
- date: the document date in YYYY-MM-DD format
- description: a brief description of the transaction

If a field cannot be determined, use an empty string for text fields and 0.0 for amount.

Document content:
{content}

Respond ONLY with a valid JSON object, no markdown or explanation."""


async def extract_finance_document(
    file_text: str,
    *,
    override_provider: str | None = None,
    override_model: str | None = None,
) -> AIFinanceExtractResult:
    """Extract financial data from document text using AI.

    Returns an AIFinanceExtractResult with confidence score.
    The result is a proposal — never auto-confirmed.
    """
    config = resolve(
        "finance_extract",
        override_provider=override_provider,
        override_model=override_model,
    )

    prompt = FINANCE_EXTRACT_PROMPT.format(content=file_text[:4000])

    try:
        result = await config.provider.generate(
            prompt,
            model=config.model,
            temperature=0.1,
            max_tokens=config.max_tokens,
            timeout_seconds=config.timeout_seconds,
        )
    except Exception:
        logger.exception("AI finance extraction failed")
        return AIFinanceExtractResult(
            confidence=0.0,
            model_version=f"{config.provider.name}:error",
            raw_extraction={"error": "provider_call_failed"},
        )

    parsed = extract_json(result.raw_text)
    if not isinstance(parsed, dict):
        logger.warning("AI returned non-dict response: %s", result.raw_text[:200])
        return AIFinanceExtractResult(
            confidence=0.0,
            model_version=f"{config.provider.name}:{result.model}",
            raw_extraction={"raw_text": result.raw_text[:500]},
        )

    confidence = 0.0
    filled_fields = 0
    for key in ("vendor_name", "amount", "date", "description"):
        val = parsed.get(key)
        if val and val != 0.0 and val != "":
            filled_fields += 1
    confidence = round(filled_fields / 4, 2)

    return AIFinanceExtractResult(
        vendor_name=str(parsed.get("vendor_name", "")),
        amount=float(parsed.get("amount", 0.0) or 0.0),
        currency=str(parsed.get("currency", "EUR") or "EUR"),
        date=str(parsed.get("date", "")),
        description=str(parsed.get("description", "")),
        confidence=confidence,
        model_version=f"{config.provider.name}:{result.model}",
        raw_extraction=parsed,
    )
