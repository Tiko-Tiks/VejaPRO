import ipaddress
import json
import logging
import os
from html import escape as html_escape
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.admin_customers import router as admin_customers_router
from app.api.v1.admin_dashboard import router as admin_dashboard_router
from app.api.v1.admin_project_details import router as admin_project_details_router
from app.api.v1.admin_search import router as admin_search_router
from app.api.v1.ai import router as ai_router
from app.api.v1.assistant import router as assistant_router
from app.api.v1.chat_webhook import router as chat_webhook_router
from app.api.v1.client_views import router as client_views_router
from app.api.v1.deploy import router as deploy_router
from app.api.v1.email_webhook import router as email_webhook_router
from app.api.v1.finance import router as finance_router
from app.api.v1.intake import router as intake_router
from app.api.v1.projects import router as projects_router
from app.api.v1.schedule import router as schedule_router
from app.api.v1.twilio_voice import router as twilio_voice_router
from app.core.config import get_settings
from app.core.dependencies import SessionLocal, get_db
from app.services.recurring_jobs import (
    start_hold_expiry_worker,
    start_notification_outbox_worker,
)
from app.services.transition_service import create_audit_log
from app.utils.rate_limit import get_client_ip, get_user_agent, is_trusted_proxy_peer, rate_limiter

settings = get_settings()
_hold_expiry_task = None
_notification_outbox_task = None

logger = logging.getLogger(__name__)

app = FastAPI(
    title="VejaPRO API",
    version="1.52-lite",
    docs_url="/docs" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.openapi_enabled else None,
)


@app.on_event("startup")
async def _startup_jobs():
    # Validate configuration on startup
    config_errors = settings.validate_required_config()
    if config_errors:
        logger.warning(
            "Configuration validation found issues:\n  - %s",
            "\n  - ".join(config_errors),
        )
        environment = os.getenv("ENVIRONMENT", "").strip().lower()
        is_production = environment in {"production", "prod"}
        if is_production:
            raise RuntimeError("Configuration validation failed in production environment: " + "; ".join(config_errors))
        logger.warning("Application started but some features may not work correctly. Please review the configuration.")

    global _hold_expiry_task, _notification_outbox_task
    if _hold_expiry_task is None and settings.enable_recurring_jobs:
        _hold_expiry_task = start_hold_expiry_worker()
    if _notification_outbox_task is None and settings.enable_recurring_jobs and settings.enable_notification_outbox:
        _notification_outbox_task = start_notification_outbox_worker()


@app.on_event("shutdown")
async def _shutdown_jobs():
    global _hold_expiry_task, _notification_outbox_task
    if _hold_expiry_task is not None:
        _hold_expiry_task.cancel()
        _hold_expiry_task = None
    if _notification_outbox_task is not None:
        _notification_outbox_task.cancel()
        _notification_outbox_task = None


if settings.cors_allow_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

app.include_router(projects_router, prefix="/api/v1", tags=["projects"])
app.include_router(client_views_router, prefix="/api/v1", tags=["client"])
app.include_router(assistant_router, prefix="/api/v1", tags=["assistant"])
app.include_router(schedule_router, prefix="/api/v1", tags=["schedule"])
app.include_router(finance_router, prefix="/api/v1", tags=["finance"])
app.include_router(twilio_voice_router, prefix="/api/v1", tags=["webhooks"])
app.include_router(chat_webhook_router, prefix="/api/v1", tags=["webhooks"])
app.include_router(email_webhook_router, prefix="/api/v1", tags=["webhooks"])
app.include_router(ai_router, prefix="/api/v1", tags=["ai"])
app.include_router(intake_router, prefix="/api/v1", tags=["intake"])
app.include_router(deploy_router, prefix="/api/v1", tags=["deploy"])
app.include_router(admin_customers_router, prefix="/api/v1", tags=["admin-customers"])
app.include_router(admin_dashboard_router, prefix="/api/v1", tags=["admin-dashboard"])
app.include_router(admin_project_details_router, prefix="/api/v1", tags=["admin-project-details"])
app.include_router(admin_search_router, prefix="/api/v1", tags=["admin-search"])

SYSTEM_ENTITY_ID = "00000000-0000-0000-0000-000000000000"
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    # Hide internal details for 5xx in production unless explicitly enabled.
    if exc.status_code >= 500 and not settings.expose_error_details:
        return JSONResponse(status_code=exc.status_code, content={"detail": "Įvyko vidinė klaida"})
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    if settings.expose_error_details:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    return JSONResponse(status_code=500, content={"detail": "Įvyko vidinė klaida"})


def _ip_in_allowlist(ip: str, allowlist: list[str]) -> bool:
    if not ip:
        return False
    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in allowlist:
        if entry == ip:
            return True
        try:
            if ip_obj in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


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


def _public_headers() -> dict:
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
            "img-src 'self' data: https://images.unsplash.com; "
            "connect-src 'self'"
        ),
    }


def _trusted_proxy_cidrs_from_settings() -> list[str]:
    cidrs = getattr(settings, "trusted_proxy_cidrs", None)
    if isinstance(cidrs, list):
        return [str(item).strip() for item in cidrs if str(item).strip()]

    raw = getattr(settings, "trusted_proxy_cidrs_raw", "")
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if not isinstance(raw, str):
        return []
    raw = raw.strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except (json.JSONDecodeError, ValueError):
        pass
    return [item.strip() for item in raw.split(",") if item.strip()]


def _client_headers() -> dict:
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
            "img-src 'self' data: https:; "
            "connect-src 'self'"
        ),
    }


def _supabase_origin() -> str:
    raw = (settings.supabase_url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.scheme:
        parsed = urlparse(f"https://{raw}")
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _login_headers() -> dict:
    connect_sources = ["'self'"]
    supabase_origin = _supabase_origin()
    if supabase_origin:
        connect_sources.append(supabase_origin)

    csp = (
        "default-src 'none'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        f"connect-src {' '.join(connect_sources)}; "
        "style-src 'self' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "object-src 'none'; "
        "form-action 'self'"
    )

    return {
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": csp,
    }


def _render_login_html() -> str:
    template = (STATIC_DIR / "login.html").read_text(encoding="utf-8")
    supabase_url = html_escape((settings.supabase_url or "").strip(), quote=True)
    supabase_anon_key = html_escape((settings.supabase_key or "").strip(), quote=True)
    rendered = template.replace("__SUPABASE_URL__", supabase_url)
    rendered = rendered.replace("__SUPABASE_ANON_KEY__", supabase_anon_key)
    return rendered


@app.middleware("http")
async def webhook_rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    if request.method != "POST":
        return await call_next(request)

    if not (
        path.startswith("/api/v1/webhook/twilio")
        or path.startswith("/api/v1/webhook/stripe")
        or path.startswith("/api/v1/webhook/email")
    ):
        return await call_next(request)

    settings = get_settings()
    if not settings.rate_limit_webhook_enabled:
        return await call_next(request)

    ip = get_client_ip(request, _trusted_proxy_cidrs_from_settings()) or "unknown"
    key = None
    limit = None
    window_seconds = 60

    if path.startswith("/api/v1/webhook/twilio"):
        key = f"twilio:ip:{ip}"
        limit = settings.rate_limit_twilio_ip_per_min
    elif path.startswith("/api/v1/webhook/stripe"):
        key = f"stripe:ip:{ip}"
        limit = settings.rate_limit_stripe_ip_per_min
    elif path.startswith("/api/v1/webhook/email"):
        key = f"email_webhook:ip:{ip}"
        limit = settings.rate_limit_email_webhook_ip_per_min

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
                        metadata={
                            "path": path,
                            "key": key,
                            "limit": limit,
                            "window_seconds": window_seconds,
                        },
                    )
                    db.commit()
                finally:
                    db.close()
            return JSONResponse(status_code=429, content={"detail": "Too Many Requests"})

    return await call_next(request)


@app.middleware("http")
async def api_rate_limit_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    if not path.startswith("/api/v1"):
        return await call_next(request)
    if path.startswith("/api/v1/webhook/twilio") or path.startswith("/api/v1/webhook/stripe"):
        return await call_next(request)

    settings = get_settings()
    if not settings.rate_limit_api_enabled:
        return await call_next(request)

    ip = get_client_ip(request, _trusted_proxy_cidrs_from_settings()) or "unknown"
    key = f"api:ip:{ip}"
    allowed, _ = rate_limiter.allow(key, settings.rate_limit_api_per_min, 60)
    if not allowed:
        return JSONResponse(status_code=429, content={"detail": "Too Many Requests"})

    return await call_next(request)


@app.middleware("http")
async def sse_token_from_query_middleware(request: Request, call_next):
    """For SSE endpoints: inject Authorization from ?token= when EventSource cannot send headers."""
    path = request.url.path
    if path in ("/api/v1/admin/finance/metrics", "/api/v1/admin/dashboard/sse"):
        token = request.query_params.get("token", "").strip()
        if token and not request.headers.get("authorization"):
            scope = request.scope
            headers = list(scope.get("headers", []))
            headers.append((b"authorization", f"Bearer {token}".encode("latin-1")))
            scope["headers"] = headers
    return await call_next(request)


@app.middleware("http")
async def staging_ip_allowlist_middleware(request: Request, call_next):
    allowlist = settings.staging_ip_allowlist
    if not allowlist:
        return await call_next(request)

    ip = (get_client_ip(request, _trusted_proxy_cidrs_from_settings()) or "").strip()
    if not _ip_in_allowlist(ip, allowlist):
        return JSONResponse(status_code=404, content={"detail": "Nerastas"})
    return await call_next(request)


@app.middleware("http")
async def admin_ip_allowlist_middleware(request: Request, call_next):
    allowlist = settings.admin_ip_allowlist
    if not allowlist:
        return await call_next(request)

    path = request.url.path
    if (
        path == "/admin"
        or path.startswith("/admin/")
        or path.startswith("/api/v1/admin/")
        or path == "/login"
        or path == "/api/v1/auth/refresh"
    ):
        # SECURITY: forwarded headers are trusted only when request comes from
        # a trusted reverse proxy (see TRUSTED_PROXY_CIDRS in settings).
        ip = (get_client_ip(request, _trusted_proxy_cidrs_from_settings()) or "").strip()
        if not _ip_in_allowlist(ip, allowlist):
            return JSONResponse(status_code=404, content={"detail": "Nerastas"})
    return await call_next(request)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    if not settings.security_headers_enabled:
        return response

    # Avoid duplicate security headers when running behind reverse proxy
    # (Nginx/edge is the canonical header source in that path).
    if is_trusted_proxy_peer(request, _trusted_proxy_cidrs_from_settings()) and (
        request.headers.get("x-forwarded-proto") or request.headers.get("x-forwarded-host")
    ):
        return response

    headers = response.headers
    if "X-Content-Type-Options" not in headers:
        headers["X-Content-Type-Options"] = "nosniff"
    if "X-Frame-Options" not in headers:
        headers["X-Frame-Options"] = "DENY"
    if "Referrer-Policy" not in headers:
        headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if "Permissions-Policy" not in headers:
        headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if "Strict-Transport-Security" not in headers:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if "Content-Security-Policy" not in headers:
        headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"

    return response


def _health_payload(db) -> tuple[dict[str, str], int]:
    from sqlalchemy import text as sa_text

    try:
        db.execute(sa_text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"
    overall = "ok" if db_status == "ok" else "degraded"
    payload = {"status": overall, "db": db_status}
    status_code = 200 if overall == "ok" else 503
    return payload, status_code


@app.get("/health")
async def health_check(db=Depends(get_db)):
    payload, _ = _health_payload(db)
    return payload


@app.head("/health")
async def health_check_head(db=Depends(get_db)):
    _, status_code = _health_payload(db)
    return Response(status_code=status_code)


@app.get("/")
async def landing_page():
    return FileResponse(STATIC_DIR / "landing.html", headers=_public_headers())


@app.get("/gallery")
async def gallery_page():
    return FileResponse(STATIC_DIR / "gallery.html", headers=_public_headers())


@app.get("/chat")
async def chat_widget_page():
    return FileResponse(STATIC_DIR / "chat.html", headers=_public_headers())


@app.get("/client")
async def client_portal():
    return FileResponse(STATIC_DIR / "client.html", headers=_client_headers())


@app.get("/contractor")
async def contractor_portal():
    return FileResponse(STATIC_DIR / "contractor.html", headers=_client_headers())


@app.get("/expert")
async def expert_portal():
    return FileResponse(STATIC_DIR / "expert.html", headers=_client_headers())


@app.get("/login")
async def login_page():
    return HTMLResponse(content=_render_login_html(), headers=_login_headers())


@app.get("/admin/audit")
async def audit_ui():
    return FileResponse(STATIC_DIR / "audit.html", headers=_admin_headers())


@app.get("/admin")
async def admin_home():
    return FileResponse(STATIC_DIR / "admin.html", headers=_admin_headers())


@app.get("/admin/projects")
async def admin_projects_ui():
    return FileResponse(STATIC_DIR / "projects.html", headers=_admin_headers())


@app.get("/admin/calls")
async def admin_calls_ui():
    return FileResponse(STATIC_DIR / "calls.html", headers=_admin_headers())


@app.get("/admin/calendar")
async def admin_calendar_ui():
    return FileResponse(STATIC_DIR / "calendar.html", headers=_admin_headers())


@app.get("/admin/margins")
async def admin_margins_ui():
    return FileResponse(STATIC_DIR / "margins.html", headers=_admin_headers())


@app.get("/admin/finance")
async def admin_finance_ui():
    return FileResponse(STATIC_DIR / "finance.html", headers=_admin_headers())


@app.get("/admin/customers")
async def admin_customers_ui():
    return FileResponse(STATIC_DIR / "customers.html", headers=_admin_headers())


@app.get("/admin/customers/{client_key}")
async def admin_customer_profile_ui(client_key: str):
    return FileResponse(STATIC_DIR / "customer-profile.html", headers=_admin_headers())


@app.get("/admin/ai")
async def admin_ai_monitor():
    return FileResponse(STATIC_DIR / "ai-monitor.html", headers=_admin_headers())


@app.get("/c3a5d76c5379841601fda497c5e89c94.html")
async def twilio_domain_verification():
    return FileResponse(STATIC_DIR / "c3a5d76c5379841601fda497c5e89c94.html")
