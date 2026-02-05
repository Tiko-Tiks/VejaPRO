from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pathlib import Path

from app.api.v1.projects import router as projects_router
from app.core.config import get_settings
from app.core.dependencies import SessionLocal
from app.core.auth import require_roles, CurrentUser
from app.services.transition_service import create_audit_log
from app.utils.rate_limit import rate_limiter, get_client_ip, get_user_agent


settings = get_settings()

app = FastAPI(
    title="VejaPRO API",
    version="1.52-lite",
    docs_url="/docs" if settings.DOCS_ENABLED else None,
    openapi_url="/openapi.json" if settings.OPENAPI_ENABLED else None,
)

if settings.cors_allow_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

app.include_router(projects_router, prefix="/api/v1", tags=["projects"])

SYSTEM_ENTITY_ID = "00000000-0000-0000-0000-000000000000"
STATIC_DIR = Path(__file__).resolve().parent / "static"


def _admin_headers() -> dict:
    return {
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        ),
    }


@app.middleware("http")
async def webhook_rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    if request.method != "POST":
        return await call_next(request)

    if path not in {"/api/v1/webhook/twilio", "/api/v1/webhook/stripe"}:
        return await call_next(request)

    settings = get_settings()
    if not settings.rate_limit_webhook_enabled:
        return await call_next(request)

    ip = get_client_ip(request) or "unknown"
    key = None
    limit = None
    window_seconds = 60

    if path.endswith("/twilio"):
        key = f"twilio:ip:{ip}"
        limit = settings.rate_limit_twilio_ip_per_min
    elif path.endswith("/stripe"):
        key = f"stripe:ip:{ip}"
        limit = settings.rate_limit_stripe_ip_per_min

    if key and limit is not None:
        allowed, _ = rate_limiter.allow(key, limit, window_seconds)
        if not allowed:
            if SessionLocal is not None:
                db = SessionLocal()
                try:
                    create_audit_log(
                        db,
                        entity_type="system",
                        entity_id=SYSTEM_ENTITY_ID,
                        action="RATE_LIMIT_BLOCKED",
                        old_value=None,
                        new_value=None,
                        actor_type="SYSTEM",
                        actor_id=None,
                        ip_address=ip,
                        user_agent=get_user_agent(request),
                        metadata={"path": path, "key": key, "limit": limit, "window_seconds": window_seconds},
                    )
                    db.commit()
                finally:
                    db.close()
            return JSONResponse(status_code=429, content={"detail": "Too Many Requests"})

    return await call_next(request)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/admin/audit")
async def audit_ui(_: CurrentUser = Depends(require_roles("ADMIN"))):
    return FileResponse(STATIC_DIR / "audit.html", headers=_admin_headers())


@app.get("/admin/projects")
async def admin_projects_ui(_: CurrentUser = Depends(require_roles("ADMIN"))):
    return FileResponse(STATIC_DIR / "projects.html", headers=_admin_headers())


@app.get("/admin/margins")
async def admin_margins_ui(_: CurrentUser = Depends(require_roles("ADMIN"))):
    return FileResponse(STATIC_DIR / "margins.html", headers=_admin_headers())
