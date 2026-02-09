import os
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
import pytest_asyncio

from app.core.config import get_settings

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")

@pytest.fixture(autouse=True)
def _reset_settings_cache():
    # Some tests mutate env vars and clear the settings cache. Ensure we don't leak
    # a cached Settings instance (e.g. with a different JWT secret) across tests.
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _has_jwt_secret() -> bool:
    return bool(os.getenv("SUPABASE_JWT_SECRET"))


def _build_auth_header(role: str | None = None) -> dict:
    """Build auth headers.

    When SUPABASE_JWT_SECRET is set, mint a real JWT.
    Otherwise, use X-Test-* headers consumed by the dependency override.
    """
    token = os.getenv("TEST_AUTH_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}

    effective_role = role or os.getenv("TEST_AUTH_ROLE", "ADMIN")
    default_sub = "00000000-0000-0000-0000-000000000001"
    if effective_role != "ADMIN":
        default_sub = "00000000-0000-0000-0000-000000000002"
    sub = os.getenv("TEST_AUTH_SUB", default_sub)

    secret = os.getenv("SUPABASE_JWT_SECRET")
    if not secret:
        # No JWT secret: rely on dependency override, pass role via custom headers.
        return {
            "X-Test-Role": effective_role,
            "X-Test-Sub": sub,
            "X-Test-Email": os.getenv("TEST_AUTH_EMAIL", "tests@example.com"),
        }

    payload = {
        "sub": sub,
        "email": os.getenv("TEST_AUTH_EMAIL", "tests@example.com"),
        "app_metadata": {"role": effective_role},
        # Keep in sync with app.core.auth.get_current_user() audience enforcement.
        "aud": os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated"),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return {"Authorization": f"Bearer {token}"}


def _install_test_auth_override():
    """Install a dependency override that reads role from X-Test-* headers.

    Called when SUPABASE_JWT_SECRET is unavailable.  Re-installs if another
    test (e.g. test_marketing_flags cleanup) cleared app.dependency_overrides.
    """
    from fastapi import Request

    from app.core.auth import CurrentUser, get_current_user
    from app.main import app

    # Always check if the override is actually present (another test may have cleared it).
    if get_current_user in app.dependency_overrides:
        return

    def _test_get_current_user(request: Request):
        role = request.headers.get("x-test-role", "ADMIN")
        sub = request.headers.get("x-test-sub", "00000000-0000-0000-0000-000000000001")
        email = request.headers.get("x-test-email", "tests@example.com")
        return CurrentUser(id=sub, role=role, email=email)

    app.dependency_overrides[get_current_user] = _test_get_current_user


async def _make_asgi_client(headers: dict):
    """Create an in-process ASGI client."""
    from app.main import app

    if not _has_jwt_secret():
        _install_test_auth_override()

    try:
        from httpx import ASGITransport

        transport = ASGITransport(app=app)
        return httpx.AsyncClient(transport=transport, base_url="http://test", headers=headers)
    except ImportError:
        return httpx.AsyncClient(app=app, base_url="http://test", headers=headers)


@pytest_asyncio.fixture
async def client():
    headers = _build_auth_header(role="ADMIN")

    # Default: in-process ASGI tests (no uvicorn needed).
    # Set USE_LIVE_SERVER=true to run against a running server at BASE_URL (useful for manual smoke tests).
    use_live_server = os.getenv("USE_LIVE_SERVER", "").strip().lower() in {"1", "true", "yes"}
    if use_live_server:
        async with httpx.AsyncClient(base_url=BASE_URL, headers=headers) as c:
            yield c
        return

    c = await _make_asgi_client(headers)
    async with c:
        yield c


@pytest_asyncio.fixture
async def subcontractor_client():
    """Client authenticated as SUBCONTRACTOR (for RBAC tests)."""
    headers = _build_auth_header(role="SUBCONTRACTOR")

    use_live_server = os.getenv("USE_LIVE_SERVER", "").strip().lower() in {"1", "true", "yes"}
    if use_live_server:
        base_url = os.getenv("BASE_URL", "http://127.0.0.1:8000")
        async with httpx.AsyncClient(base_url=base_url, headers=headers) as c:
            yield c
        return

    c = await _make_asgi_client(headers)
    async with c:
        yield c
