import os
from datetime import datetime, timedelta, timezone

import jwt
import pytest_asyncio
from httpx import AsyncClient

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
    async with AsyncClient(base_url=BASE_URL, headers=headers) as c:
        yield c
