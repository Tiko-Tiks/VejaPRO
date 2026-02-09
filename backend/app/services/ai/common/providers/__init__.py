"""Provider factory — returns the right provider instance or falls back to mock."""

from __future__ import annotations

import logging

from app.core.config import get_settings

from .base import BaseProvider, ProviderResult
from .mock import MockProvider

logger = logging.getLogger(__name__)

__all__ = ["get_provider", "BaseProvider", "ProviderResult", "MockProvider"]


def get_provider(provider_name: str) -> BaseProvider:
    """Return a provider instance for *provider_name*.

    If the requested provider is not in the allowlist, has no API key,
    or fails to initialise, we silently fall back to ``MockProvider``.
    """
    settings = get_settings()
    name = provider_name.lower().strip()

    if name not in settings.ai_allowed_providers:
        logger.warning("Provider %r not in allowlist – falling back to mock", name)
        return MockProvider()

    if name == "mock":
        return MockProvider()

    if name == "claude":
        if not settings.anthropic_api_key:
            logger.warning("ANTHROPIC_API_KEY not set – falling back to mock")
            return MockProvider()
        from .claude import ClaudeProvider

        return ClaudeProvider(api_key=settings.anthropic_api_key)

    if name == "groq":
        if not settings.groq_api_key:
            logger.warning("GROQ_API_KEY not set – falling back to mock")
            return MockProvider()
        from .groq import GroqProvider

        return GroqProvider(api_key=settings.groq_api_key)

    if name == "openai":
        if not settings.openai_api_key:
            logger.warning("OPENAI_API_KEY not set – falling back to mock")
            return MockProvider()
        from .openai import OpenAIProvider

        return OpenAIProvider(api_key=settings.openai_api_key)

    logger.warning("Unknown provider %r – falling back to mock", name)
    return MockProvider()
