import os
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest_asyncio

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")


def _build_auth_header() -> dict:
    token = os.getenv("TEST_AUTH_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}

    secret = os.getenv("SUPABASE_JWT_SECRET")
    if not secret:
        return {}

    role = os.getenv("TEST_AUTH_ROLE", "ADMIN")
    payload = {
        "sub": os.getenv("TEST_AUTH_SUB", "00000000-0000-0000-0000-000000000001"),
        "email": os.getenv("TEST_AUTH_EMAIL", "tests@example.com"),
        "app_metadata": {"role": role},
        # Keep in sync with app.core.auth.get_current_user() audience enforcement.
        "aud": os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated"),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def client():
    headers = _build_auth_header()

    # Default: in-process ASGI tests (no uvicorn needed).
    # Set USE_LIVE_SERVER=true to run against a running server at BASE_URL (useful for manual smoke tests).
    use_live_server = os.getenv("USE_LIVE_SERVER", "").strip().lower() in {"1", "true", "yes"}
    if use_live_server:
        async with httpx.AsyncClient(base_url=BASE_URL, headers=headers) as c:
            yield c
        return

    from app.main import app

    try:
        from httpx import ASGITransport

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", headers=headers) as c:
            yield c
    except ImportError:
        # Backward-compat for older httpx versions.
        async with httpx.AsyncClient(app=app, base_url="http://test", headers=headers) as c:
            yield c
