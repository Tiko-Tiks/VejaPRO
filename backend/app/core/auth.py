from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException

from app.core.config import get_settings

ALLOWED_ROLES = {"CLIENT", "SUBCONTRACTOR", "EXPERT", "ADMIN"}


@dataclass
class CurrentUser:
    id: str
    role: str
    email: Optional[str] = None


def _extract_role(payload: dict) -> Optional[str]:
    # SECURITY: role must come only from server-managed app_metadata.
    # user_metadata is user-editable in Supabase Auth and cannot be trusted for RBAC.
    app_meta = payload.get("app_metadata") or {}
    raw = app_meta.get("role")
    if raw is None:
        return None
    role = str(raw).strip().upper()
    if role not in ALLOWED_ROLES:
        return None
    return role


def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Trūksta „Bearer“ žetono")

    token = authorization.split(" ", 1)[1].strip()
    settings = get_settings()
    if not settings.supabase_jwt_secret:
        raise HTTPException(500, "Nesukonfigūruotas SUPABASE_JWT_SECRET")

    try:
        audience = (settings.supabase_jwt_audience or "").strip()
        decode_kwargs = {}
        options = {}
        if audience:
            decode_kwargs["audience"] = audience
            options["verify_aud"] = True
        else:
            # Backward compatibility: if no audience is configured, do not enforce aud.
            options["verify_aud"] = False

        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options=options,
            **decode_kwargs,
        )
    except (jwt.InvalidTokenError, jwt.DecodeError, jwt.ExpiredSignatureError) as exc:
        raise HTTPException(401, "Netinkamas žetonas") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(401, "Netinkamas žetonas")

    role = _extract_role(payload)
    if not role:
        raise HTTPException(403, "Trūksta rolės")

    return CurrentUser(id=user_id, role=role, email=payload.get("email"))


def require_roles(*roles: str):
    def _dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(403, "Draudžiama")
        return user

    return _dependency
