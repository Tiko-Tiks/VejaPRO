import jwt
import pytest
from fastapi import HTTPException

from app.core.auth import get_current_user
from app.core.config import get_settings


def _make_token(
    secret: str,
    aud: str,
    *,
    app_role: str | None = "ADMIN",
    user_role: str | None = None,
) -> str:
    app_meta = {}
    if app_role is not None:
        app_meta["role"] = app_role
    user_meta = {}
    if user_role is not None:
        user_meta["role"] = user_role

    payload = {
        "sub": "00000000-0000-0000-0000-000000000123",
        "email": "admin@test.local",
        "app_metadata": app_meta,
        "user_metadata": user_meta,
        "aud": aud,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def test_get_current_user_accepts_matching_audience(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret")
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    get_settings.cache_clear()

    token = _make_token("test-secret", "authenticated")
    user = get_current_user(authorization=f"Bearer {token}")
    assert user.role == "ADMIN"


def test_get_current_user_rejects_wrong_audience(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret")
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    get_settings.cache_clear()

    token = _make_token("test-secret", "other")
    with pytest.raises(HTTPException) as exc:
        get_current_user(authorization=f"Bearer {token}")
    assert exc.value.status_code == 401


def test_get_current_user_ignores_user_metadata_role(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret")
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    get_settings.cache_clear()

    token = _make_token("test-secret", "authenticated", app_role=None, user_role="ADMIN")
    with pytest.raises(HTTPException) as exc:
        get_current_user(authorization=f"Bearer {token}")
    assert exc.value.status_code == 403
