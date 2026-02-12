from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_startup_fails_fast_on_config_errors_in_production(monkeypatch):
    from app import main as app_main

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(type(app_main.settings), "validate_required_config", lambda _self: ["missing secret"])

    with pytest.raises(RuntimeError, match="Configuration validation failed in production environment"):
        await app_main._startup_jobs()


@pytest.mark.asyncio
async def test_startup_logs_warning_only_on_config_errors_in_test(monkeypatch):
    from app import main as app_main

    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setattr(type(app_main.settings), "validate_required_config", lambda _self: ["missing secret"])

    await app_main._startup_jobs()
