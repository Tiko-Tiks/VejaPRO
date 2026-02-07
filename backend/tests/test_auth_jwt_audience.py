import jwt
import pytest
from fastapi import HTTPException

from app.core.auth import get_current_user
from app.core.config import get_settings


def _make_token(secret: str, aud: str) -> str:
    payload = {
        "sub": "00000000-0000-0000-0000-000000000123",
        "email": "admin@test.local",
        "app_metadata": {"role": "ADMIN"},
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
