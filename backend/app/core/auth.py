from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException
import jwt

from app.core.config import get_settings


@dataclass
class CurrentUser:
    id: str
    role: str
    email: Optional[str] = None


def _extract_role(payload: dict) -> Optional[str]:
    app_meta = payload.get("app_metadata") or {}
    user_meta = payload.get("user_metadata") or {}
    return app_meta.get("role") or user_meta.get("role")


def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    settings = get_settings()
    if not settings.supabase_jwt_secret:
        raise HTTPException(500, "SUPABASE_JWT_SECRET is not configured")

    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except Exception as exc:
        raise HTTPException(401, "Invalid token") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(401, "Invalid token")

    role = _extract_role(payload)
    if not role:
        raise HTTPException(403, "Missing role")

    return CurrentUser(id=user_id, role=role, email=payload.get("email"))


def require_roles(*roles: str):
    def _dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(403, "Forbidden")
        return user

    return _dependency
