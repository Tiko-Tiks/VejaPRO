"""AI audit — writes AI_RUN entries to the existing audit_logs table."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.transition_service import create_audit_log

from .providers.base import ProviderResult

logger = logging.getLogger(__name__)


def log_ai_run(
    db: Session,
    *,
    scope: str,
    provider_result: ProviderResult,
    prompt_text: str,
    parsed_output: dict[str, Any] | None,
    actor_id: str | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> None:
    """Write an ``AI_RUN`` audit entry.

    * ``scope`` — e.g. ``"intent"``, ``"vision"``, ``"finance_extract"``.
    * PII: prompt text is always hashed; raw text is only stored when
      ``AI_DEBUG_STORE_RAW=true``.
    """
    settings = get_settings()

    prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()
    response_hash = hashlib.sha256(provider_result.raw_text.encode()).hexdigest()

    metadata: dict[str, Any] = {
        "scope": scope,
        "provider": provider_result.provider,
        "model": provider_result.model,
        "prompt_tokens": provider_result.prompt_tokens,
        "completion_tokens": provider_result.completion_tokens,
        "latency_ms": provider_result.latency_ms,
        "prompt_hash": prompt_hash,
        "response_hash": response_hash,
    }

    if settings.ai_debug_store_raw:
        metadata["prompt_raw"] = prompt_text
        metadata["response_raw"] = provider_result.raw_text

    if extra_meta:
        metadata.update(extra_meta)

    create_audit_log(
        db,
        entity_type="ai",
        entity_id=scope,
        action="AI_RUN",
        old_value=None,
        new_value=parsed_output,
        actor_type="SYSTEM",
        actor_id=actor_id,
        ip_address=None,
        user_agent=None,
        metadata=metadata,
    )
