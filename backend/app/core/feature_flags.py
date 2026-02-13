from fastapi import HTTPException

from app.core.config import get_settings


def ensure_admin_ops_v1_enabled() -> None:
    settings = get_settings()
    if not settings.enable_admin_ops_v1:
        raise HTTPException(status_code=404, detail="Nerastas")
