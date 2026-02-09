"""AI Router — resolves provider + model with override > ENV > prod-fallback chain."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import get_settings

from .providers import BaseProvider, get_provider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedConfig:
    """Final resolved provider + model after the override chain."""

    provider: BaseProvider
    model: str
    temperature: float
    max_tokens: int
    timeout_seconds: float


def resolve(
    scope: str,
    *,
    override_provider: str | None = None,
    override_model: str | None = None,
) -> ResolvedConfig:
    """Resolve provider + model for a given *scope*.

    Resolution chain (first non-empty wins):
      1. ``override_provider`` / ``override_model`` (runtime request param,
         only when ``enable_ai_overrides=True``).
      2. ENV scope-specific: e.g. ``AI_INTENT_PROVIDER`` / ``AI_INTENT_MODEL``.
      3. Prod fallback: ``"mock"`` with empty model.

    Model validation: if the resolved model is not in the allowlist for
    that provider, we fall back to the first allowed model (or empty for mock).
    """
    settings = get_settings()

    # --- 1. Determine provider name ---
    provider_name = ""

    if settings.enable_ai_overrides and override_provider:
        provider_name = override_provider.lower().strip()

    if not provider_name and scope == "intent":
        provider_name = settings.ai_intent_provider

    if not provider_name:
        provider_name = "mock"

    # --- 2. Determine model ---
    model = ""

    if settings.enable_ai_overrides and override_model:
        model = override_model.strip()

    if not model and scope == "intent":
        model = settings.ai_intent_model

    # --- 3. Validate model against allowlist ---
    allowed_models = settings.ai_allowed_models.get(provider_name, [])
    if allowed_models and model and model not in allowed_models:
        logger.warning(
            "Model %r not in allowlist for %r — using first allowed: %r",
            model,
            provider_name,
            allowed_models[0],
        )
        model = allowed_models[0]

    if allowed_models and not model:
        model = allowed_models[0]

    # --- 4. Resolve scope-specific timeout ---
    timeout = settings.ai_timeout_seconds
    if scope == "intent":
        timeout = settings.ai_intent_timeout_seconds

    # --- 5. Build provider instance ---
    provider = get_provider(provider_name)

    return ResolvedConfig(
        provider=provider,
        model=model,
        temperature=settings.ai_temperature,
        max_tokens=settings.ai_max_tokens,
        timeout_seconds=timeout,
    )
