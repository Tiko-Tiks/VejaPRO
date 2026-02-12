from __future__ import annotations

import httpx
import pytest


class _MockResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _MockAsyncClient:
    def __init__(self, *, response=None, error: Exception | None = None, **kwargs):
        self._response = response
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        if self._error is not None:
            raise self._error
        return self._response


def _patch_async_client(monkeypatch, response=None, error: Exception | None = None):
    def _factory(*args, **kwargs):
        return _MockAsyncClient(response=response, error=error, **kwargs)

    monkeypatch.setattr("app.api.v1.projects.httpx.AsyncClient", _factory)


@pytest.mark.asyncio
async def test_auth_refresh_invalid_json_returns_400(client):
    resp = await client.post(
        "/api/v1/auth/refresh",
        content="not-json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_auth_refresh_missing_token_returns_400(client):
    resp = await client.post("/api/v1/auth/refresh", json={})
    assert resp.status_code == 400
    assert "refresh_token" in resp.text


@pytest.mark.asyncio
async def test_auth_refresh_supabase_non_200_returns_401(client, monkeypatch):
    _patch_async_client(monkeypatch, response=_MockResponse(401, {"error": "invalid_grant"}))
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "bad-token"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_refresh_request_error_returns_502(client, monkeypatch):
    _patch_async_client(
        monkeypatch,
        error=httpx.RequestError("network down", request=httpx.Request("POST", "https://example.com")),
    )
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "rt-1"})
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_auth_refresh_success_with_expires_at(client, monkeypatch):
    payload = {
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "expires_at": 1890000000,
    }
    _patch_async_client(monkeypatch, response=_MockResponse(200, payload))

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "old-refresh"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"] == "new-access"
    assert data["refresh_token"] == "new-refresh"
    assert data["expires_at"] == 1890000000


@pytest.mark.asyncio
async def test_auth_refresh_success_expires_in_converted_to_expires_at(client, monkeypatch):
    payload = {
        "access_token": "new-access",
        "expires_in": 1200,
    }
    _patch_async_client(monkeypatch, response=_MockResponse(200, payload))

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "old-refresh"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"] == "new-access"
    assert data["refresh_token"] == "old-refresh"
    assert isinstance(data["expires_at"], int)
    assert data["expires_at"] > 0
