"""Intent classification service with budget-based retry and audit."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings

from ..common import router as ai_router
from ..common.audit import log_ai_run
from ..common.json_tools import extract_json
from ..common.providers.base import ProviderResult
from .contracts import AIIntentResult

logger = logging.getLogger(__name__)

INTENT_SYSTEM_PROMPT = (
    "You are a phone call intent classifier for a construction/certification company. "
    "Classify the caller's intent into one of: schedule_visit, request_quote, "
    "check_status, complaint, general_inquiry, cancel, reschedule. "
    "Return ONLY a JSON object with keys: intent, confidence (0.0-1.0), params (object). "
    'Example: {"intent": "schedule_visit", "confidence": 0.85, "params": {"preferred_date": "2025-01-15"}}'
)


@dataclass
class IntentServiceResult:
    """Result from ``parse_intent`` including metadata."""

    intent_result: AIIntentResult
    provider_result: ProviderResult
    attempts: int
    total_latency_ms: float


async def parse_intent(
    text: str,
    db: Session,
    *,
    override_provider: str | None = None,
    override_model: str | None = None,
    actor_id: str | None = None,
) -> IntentServiceResult:
    """Parse caller intent from *text* with budget-based retry.

    Budget logic:
      - ``ai_intent_budget_seconds`` = total wall-clock budget (default 2.0s).
      - ``ai_intent_timeout_seconds`` = per-call timeout (default 1.2s).
      - Retry if remaining budget > 0.5s AND attempts < ``ai_intent_max_retries + 1``.
    """
    settings = get_settings()
    budget = settings.ai_intent_budget_seconds
    max_attempts = settings.ai_intent_max_retries + 1

    config = ai_router.resolve(
        "intent",
        override_provider=override_provider,
        override_model=override_model,
    )

    prompt = f'{INTENT_SYSTEM_PROMPT}\n\nCaller said: "{text}"'

    t0 = time.monotonic()
    attempts = 0
    last_result: ProviderResult | None = None
    last_error: Exception | None = None

    while attempts < max_attempts:
        elapsed = time.monotonic() - t0
        remaining = budget - elapsed
        if attempts > 0 and remaining < 0.5:
            logger.info(
                "Budget exhausted (%.2fs remaining) — stopping retries", remaining
            )
            break

        attempts += 1
        try:
            last_result = await config.provider.generate(
                prompt,
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                timeout_seconds=config.timeout_seconds,
            )

            parsed = extract_json(last_result.raw_text)
            if parsed and isinstance(parsed, dict):
                intent = AIIntentResult.model_validate(parsed)
                total_ms = (time.monotonic() - t0) * 1000

                log_ai_run(
                    db,
                    scope="intent",
                    provider_result=last_result,
                    prompt_text=prompt,
                    parsed_output=intent.model_dump(),
                    actor_id=actor_id,
                    extra_meta={"attempts": attempts, "input_text": text},
                )

                return IntentServiceResult(
                    intent_result=intent,
                    provider_result=last_result,
                    attempts=attempts,
                    total_latency_ms=round(total_ms, 2),
                )

            logger.warning("Attempt %d: could not parse JSON from response", attempts)
            last_error = ValueError("No valid JSON in response")

        except Exception as exc:
            logger.warning("Attempt %d failed: %s", attempts, exc)
            last_error = exc

    # All attempts exhausted — fall back to mock result
    total_ms = (time.monotonic() - t0) * 1000
    logger.warning("All %d attempts failed — returning fallback mock result", attempts)

    fallback_result = last_result or ProviderResult(
        raw_text="{}",
        model="fallback",
        provider="mock",
    )

    fallback_intent = AIIntentResult(
        intent="general_inquiry",
        confidence=0.0,
        params={
            "fallback": True,
            "error": str(last_error) if last_error else "unknown",
        },
    )

    log_ai_run(
        db,
        scope="intent",
        provider_result=fallback_result,
        prompt_text=prompt,
        parsed_output=fallback_intent.model_dump(),
        actor_id=actor_id,
        extra_meta={"attempts": attempts, "fallback": True, "input_text": text},
    )

    return IntentServiceResult(
        intent_result=fallback_intent,
        provider_result=fallback_result,
        attempts=attempts,
        total_latency_ms=round(total_ms, 2),
    )
