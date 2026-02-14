from __future__ import annotations

import httpx
import pytest

from app.main import app


def _make_httpx_client(*, headers: dict | None = None) -> httpx.AsyncClient:
    try:
        from httpx import ASGITransport

        return httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers=headers,
        )
    except ImportError:
        return httpx.AsyncClient(app=app, base_url="http://test", headers=headers)


@pytest.mark.asyncio
async def test_auth_me_returns_current_admin_user(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["role"] == "ADMIN"
    assert payload["user_id"]


@pytest.mark.asyncio
async def test_auth_me_requires_bearer_token():
    async with _make_httpx_client() as anonymous_client:
        response = await anonymous_client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_returns_non_admin_role(subcontractor_client):
    response = await subcontractor_client.get("/api/v1/auth/me")
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["role"] == "SUBCONTRACTOR"
    assert payload["user_id"]
