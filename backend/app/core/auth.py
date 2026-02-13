import logging
import threading
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException
from jwt import PyJWKClient

from app.core.config import get_settings

logger = logging.getLogger(__name__)

ALLOWED_ROLES = {"CLIENT", "SUBCONTRACTOR", "EXPERT", "ADMIN"}

# Thread-safe JWKS client cache (initialised lazily, lives for process lifetime).
_jwks_client: Optional[PyJWKClient] = None
_jwks_lock = threading.Lock()


def _get_jwks_client(jwks_url: str) -> PyJWKClient:
    """Return a cached PyJWKClient (with built-in key caching)."""
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client
    with _jwks_lock:
        if _jwks_client is not None:
            return _jwks_client
        _jwks_client = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
        return _jwks_client


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


def _decode_options(settings):
    """Build shared audience kwargs + options dict."""
    audience = (settings.supabase_jwt_audience or "").strip()
    decode_kwargs = {}
    options = {}
    if audience:
        decode_kwargs["audience"] = audience
        options["verify_aud"] = True
    else:
        options["verify_aud"] = False
    return decode_kwargs, options


def _try_hs256(token: str, settings, decode_kwargs: dict, options: dict):
    """Attempt HS256 verification with supabase_jwt_secret. Returns payload or None."""
    try:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options=options,
            **decode_kwargs,
        )
    except (jwt.InvalidTokenError, jwt.DecodeError, jwt.ExpiredSignatureError):
        return None


def _try_es256(token: str, settings, decode_kwargs: dict, options: dict):
    """Attempt ES256 verification via Supabase JWKS endpoint. Returns payload or None."""
    supabase_url = (settings.supabase_url or "").rstrip("/")
    if not supabase_url:
        return None
    jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
    try:
        client = _get_jwks_client(jwks_url)
        signing_key = client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            options=options,
            **decode_kwargs,
        )
    except Exception as exc:
        logger.debug("ES256 verification failed: %s", exc)
        return None


def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Truksta Bearer zetono")

    token = authorization.split(" ", 1)[1].strip()
    settings = get_settings()

    # Need at least one verification method configured
    if not settings.supabase_jwt_secret and not settings.supabase_url:
        raise HTTPException(500, "Nesukonfigūruotas SUPABASE_JWT_SECRET")

    decode_kwargs, options = _decode_options(settings)

    # Peek at token header to choose strategy order (avoids unnecessary network calls)
    try:
        header = jwt.get_unverified_header(token)
    except jwt.DecodeError:
        raise HTTPException(401, "Netinkamas žetonas")

    alg = header.get("alg", "")

    payload = None
    if alg == "ES256":
        payload = _try_es256(token, settings, decode_kwargs, options)
        if payload is None and settings.supabase_jwt_secret:
            payload = _try_hs256(token, settings, decode_kwargs, options)
    else:
        if settings.supabase_jwt_secret:
            payload = _try_hs256(token, settings, decode_kwargs, options)
        if payload is None:
            payload = _try_es256(token, settings, decode_kwargs, options)

    if payload is None:
        raise HTTPException(401, "Netinkamas žetonas")

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
