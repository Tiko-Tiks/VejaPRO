"""AI Email Sentiment Classification service.

Classifies inbound email sentiment as NEGATIVE / NEUTRAL / POSITIVE.
Results stored in CallRequest.intake_state["sentiment_analysis"].

Features:
- Idempotency via source_message_id (prevents AI cost explosion on retries)
- Compare-and-set after AI call (handles concurrent webhook retries)
- Tolerant JSON parsing (fence removal, substring extraction)
- Input truncation (quoted thread removal, max 8000 chars)
- Success-only audit (failure logged via logger.warning, no audit noise)
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.project import CallRequest
from app.services.ai.common import router as ai_router
from app.services.ai.common.audit import log_ai_run

from .contracts import MAX_REASON_CODES, VALID_LABELS, VALID_REASON_CODES, SentimentResult

logger = logging.getLogger(__name__)

MAX_SENTIMENT_INPUT_CHARS = 8000
_QUOTED_THREAD_RE = re.compile(r"^On .+ wrote:\s*$", re.IGNORECASE)
_ORIGINAL_MSG_RE = re.compile(r"^-{3,}\s*Original Message\s*-{3,}", re.IGNORECASE)

SENTIMENT_SYSTEM_PROMPT = (
    "You are a sentiment classifier for customer emails to a lawn care service.\n"
    "Classify the sentiment. Return ONLY valid JSON, no other text.\n\n"
    'Schema: {"label": "NEGATIVE|NEUTRAL|POSITIVE", "confidence": 0.0-1.0, "reason_codes": [...]}\n'
    "Valid reason_codes (only for NEGATIVE): DELAY, QUALITY, PRICING, RUDENESS, FRUSTRATION, THREAT, OTHER\n"
    "For NEUTRAL or POSITIVE, use empty reason_codes array."
)


def _normalize_message_id(mid: str | None) -> str | None:
    """Normalize Message-Id: strip whitespace, keep <> as-is."""
    if not mid:
        return None
    return mid.strip()


def _prepare_text(text: str) -> str:
    """Remove quoted thread history and truncate for sentiment analysis."""
    lines = text.split("\n")
    clean: list[str] = []
    for line in lines:
        stripped = line.strip()
        # Stop at "On ... wrote:" or "--- Original Message ---"
        if _QUOTED_THREAD_RE.match(stripped) or _ORIGINAL_MSG_RE.match(stripped):
            break
        # Skip > quoted lines
        if stripped.startswith(">"):
            continue
        clean.append(line)
    result = "\n".join(clean).strip()
    return result[:MAX_SENTIMENT_INPUT_CHARS]


def _extract_json(raw: str) -> dict[str, Any] | None:
    """Tolerant JSON extraction: handles fences, trailing text."""
    s = raw.strip()
    # Remove ```json ... ``` or ``` ... ```
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    # Find first { and last }
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(s[start : end + 1])
    except json.JSONDecodeError:
        return None


def _validate_and_enforce(parsed: dict[str, Any]) -> SentimentResult | None:
    """Validate parsed JSON and enforce business rules."""
    label = str(parsed.get("label", "")).upper().strip()
    if label not in VALID_LABELS:
        return None

    # Clamp confidence 0.0–1.0
    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (ValueError, TypeError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    # Process reason_codes
    raw_codes = parsed.get("reason_codes") or []
    if not isinstance(raw_codes, list):
        raw_codes = []

    # Dedup preserving order
    seen: set[str] = set()
    reason_codes: list[str] = []
    for code in raw_codes:
        c = str(code).upper().strip()
        if c not in seen:
            seen.add(c)
            reason_codes.append(c)

    # Filter to valid codes only
    reason_codes = [r for r in reason_codes if r in VALID_REASON_CODES]

    # Enforce: NEUTRAL/POSITIVE → empty reason_codes
    if label != "NEGATIVE":
        reason_codes = []

    # Truncate
    reason_codes = reason_codes[:MAX_REASON_CODES]

    return SentimentResult(label=label, confidence=confidence, reason_codes=reason_codes)


async def classify_email_sentiment(
    text: str,
    db: Session,
    *,
    call_request_id: str,
    message_id: str | None = None,
) -> SentimentResult | None:
    """Classify email sentiment and write result to intake_state.

    Returns:
        SentimentResult if classified successfully, None otherwise.
    """
    settings = get_settings()
    if not settings.enable_ai_email_sentiment:
        return None

    normalized_mid = _normalize_message_id(message_id)

    # Load CallRequest
    cr = db.get(CallRequest, call_request_id)
    if not cr:
        logger.warning("Sentiment: CR %s not found", call_request_id)
        return None

    state = dict(cr.intake_state or {})

    # --- Pre-call idempotency check ---
    existing = state.get("sentiment_analysis") or {}
    if normalized_mid and existing.get("source_message_id") == normalized_mid:
        # Already classified for this message — return cached result
        return SentimentResult(
            label=existing.get("label", "NEUTRAL"),
            confidence=existing.get("confidence", 0.0),
            reason_codes=existing.get("reason_codes", []),
        )

    # --- Prepare text (truncate, remove quoted history) ---
    prepared = _prepare_text(text)
    if not prepared:
        return None

    # --- Resolve AI provider ---
    config = ai_router.resolve("sentiment")

    prompt = f'{SENTIMENT_SYSTEM_PROMPT}\n\nEmail text:\n"""\n{prepared}\n"""'

    # --- Call AI provider ---
    t0 = time.monotonic()
    try:
        provider_result = await config.provider.generate(
            prompt,
            model=config.model,
            temperature=0,
            max_tokens=256,
            timeout_seconds=config.timeout_seconds,
        )
    except Exception:
        logger.warning("Sentiment provider failed for cr=%s", call_request_id, exc_info=True)
        return None

    latency_ms = int((time.monotonic() - t0) * 1000)

    # --- Parse response ---
    parsed = _extract_json(provider_result.raw_text)
    if not parsed:
        logger.warning("Sentiment: could not parse JSON from response for cr=%s", call_request_id)
        return None

    result = _validate_and_enforce(parsed)
    if not result:
        logger.warning("Sentiment: validation failed for cr=%s", call_request_id)
        return None

    # --- Compare-and-Set: reload CR to handle concurrent writes ---
    db.refresh(cr)
    reloaded_state = dict(cr.intake_state or {})
    reloaded_existing = reloaded_state.get("sentiment_analysis") or {}
    if normalized_mid and reloaded_existing.get("source_message_id") == normalized_mid:
        # Another concurrent request already wrote this — return cached
        return SentimentResult(
            label=reloaded_existing.get("label", "NEUTRAL"),
            confidence=reloaded_existing.get("confidence", 0.0),
            reason_codes=reloaded_existing.get("reason_codes", []),
        )

    # --- Write to intake_state (merge, don't overwrite) ---
    classified_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    reloaded_state["sentiment_analysis"] = {
        "label": result.label,
        "confidence": result.confidence,
        "reason_codes": result.reason_codes,
        "source_message_id": normalized_mid,
        "model": config.model or provider_result.model,
        "provider": provider_result.provider,
        "latency_ms": latency_ms,
        "classified_at": classified_at,
    }

    cr.intake_state = reloaded_state
    db.add(cr)
    db.flush()

    # --- Audit (success only, same transaction, no commit) ---
    log_ai_run(
        db,
        scope="sentiment",
        provider_result=provider_result,
        prompt_text=prompt,
        parsed_output={
            "label": result.label,
            "confidence": result.confidence,
            "reason_codes": result.reason_codes,
        },
        extra_meta={
            "call_request_id": call_request_id,
            "source_message_id": normalized_mid,
            "latency_ms": latency_ms,
        },
    )

    return result
