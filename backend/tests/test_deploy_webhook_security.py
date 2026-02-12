import asyncio

import pytest

from app.core.config import get_settings


class _FakeProc:
    def __init__(self, returncode: int, output: bytes) -> None:
        self.returncode = returncode
        self._output = output

    async def communicate(self):
        return self._output, b""


@pytest.mark.asyncio
async def test_deploy_webhook_invalid_token_returns_404(client, monkeypatch):
    monkeypatch.setenv("DEPLOY_WEBHOOK_SECRET", "top-secret")
    get_settings.cache_clear()

    resp = await client.post("/api/v1/deploy/webhook", headers={"X-Deploy-Token": "wrong"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_deploy_webhook_hides_script_output_by_default(client, monkeypatch):
    monkeypatch.setenv("DEPLOY_WEBHOOK_SECRET", "top-secret")
    monkeypatch.setenv("EXPOSE_ERROR_DETAILS", "false")
    get_settings.cache_clear()

    async def _fake_create_subprocess_exec(*_args, **_kwargs):
        return _FakeProc(0, b"ok: secret_like_value=abc123")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    resp = await client.post("/api/v1/deploy/webhook", headers={"X-Deploy-Token": "top-secret"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["exit_code"] == 0
    assert "output" not in body


@pytest.mark.asyncio
async def test_deploy_webhook_can_include_output_when_exposed(client, monkeypatch):
    monkeypatch.setenv("DEPLOY_WEBHOOK_SECRET", "top-secret")
    monkeypatch.setenv("EXPOSE_ERROR_DETAILS", "true")
    get_settings.cache_clear()

    async def _fake_create_subprocess_exec(*_args, **_kwargs):
        return _FakeProc(1, b"boom")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    resp = await client.post("/api/v1/deploy/webhook", headers={"X-Deploy-Token": "top-secret"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "error"
    assert body["exit_code"] == 1
    assert body["output"] == "boom"
