import base64
import csv
import io
import json
import re
import time
import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

import jwt
import stripe
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session, aliased
from twilio.request_validator import RequestValidator

from app.core.auth import CurrentUser, get_current_user, require_roles
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.core.storage import upload_evidence_file
from app.models.project import AuditLog, Evidence, Margin, Payment, Project, User
from app.schemas.project import (
    AdminProjectListResponse,
    AdminProjectOut,
    ApproveEvidenceRequest,
    AssignRequest,
    AuditLogListResponse,
    AuditLogOut,
    CertifyRequest,
    CertifyResponse,
    ClientProjectListResponse,
    EvidenceCategory,
    EvidenceOut,
    GalleryItem,
    GalleryResponse,
    ManualPaymentRequest,
    ManualPaymentResponse,
    MarginCreateRequest,
    MarginListResponse,
    MarginOut,
    MarketingConsentOut,
    MarketingConsentRequest,
    PaymentLinkRequest,
    PaymentLinkResponse,
    PaymentType,
    ProjectCreate,
    ProjectDetail,
    ProjectOut,
    ProjectStatus,
    TransitionRequest,
    UploadEvidenceResponse,
)
from app.services.sms_service import send_sms
from app.services.transition_service import (
    apply_transition,
    create_audit_log,
    create_sms_confirmation,
    find_sms_confirmation,
    increment_sms_attempt,
    is_final_payment_recorded,
    unpublish_project_evidences,
)
from app.services.vision_service import analyze_site_photo
from app.utils.pdf_gen import generate_certificate_pdf
from app.utils.rate_limit import rate_limiter

router = APIRouter()
SYSTEM_ENTITY_ID = "00000000-0000-0000-0000-000000000000"
MAX_EVIDENCE_FILE_BYTES = 10 * 1024 * 1024
ALLOWED_ACTOR_OVERRIDES = {
    "SYSTEM_STRIPE",
    "SYSTEM_TWILIO",
    "CLIENT",
    "SUBCONTRACTOR",
    "EXPERT",
    "ADMIN",
}


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _user_agent(request: Request) -> Optional[str]:
    return request.headers.get("user-agent") if request else None


def _user_fk_or_none(db: Session, user_id: str) -> uuid.UUID | None:
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        return None
    return user_uuid if db.get(User, user_uuid) else None


def _twilio_request_url(request: Request) -> str:
    url = request.url
    proto = request.headers.get("x-forwarded-proto")
    host = request.headers.get("x-forwarded-host")
    if proto:
        url = url.replace(scheme=proto)
    if host:
        url = url.replace(netloc=host)
    return str(url)


def _twilio_empty_response() -> Response:
    return Response(content="<Response></Response>", media_type="application/xml")


def _encode_cursor(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    payload = dt.isoformat().encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("utf-8")


def _decode_cursor(value: str) -> datetime:
    try:
        raw = base64.urlsafe_b64decode(value.encode("utf-8")).decode("utf-8")
        parsed = datetime.fromisoformat(raw)
    except Exception as exc:
        raise HTTPException(400, "Neteisingas žymeklis") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _encode_audit_cursor(ts: datetime, log_id: str) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    payload = f"{ts.isoformat()}|{log_id}".encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("utf-8")


def _decode_audit_cursor(value: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(value.encode("utf-8")).decode("utf-8")
        ts_raw, id_raw = raw.split("|", 1)
        parsed = datetime.fromisoformat(ts_raw)
        log_id = uuid.UUID(id_raw)
    except Exception as exc:
        raise HTTPException(400, "Neteisingas žymeklis") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed, log_id


def _encode_project_cursor(ts: datetime, project_id: str) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    payload = f"{ts.isoformat()}|{project_id}".encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("utf-8")


def _decode_project_cursor(value: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(value.encode("utf-8")).decode("utf-8")
        ts_raw, id_raw = raw.split("|", 1)
        parsed = datetime.fromisoformat(ts_raw)
        project_id = uuid.UUID(id_raw)
    except Exception as exc:
        raise HTTPException(400, "Neteisingas žymeklis") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed, project_id


def _project_to_out(project: Project) -> ProjectOut:
    return ProjectOut(
        id=str(project.id),
        client_info=project.client_info,
        status=ProjectStatus(project.status),
        area_m2=project.area_m2,
        total_price_client=project.total_price_client,
        internal_cost=project.internal_cost,
        vision_analysis=project.vision_analysis,
        has_robot=bool(project.has_robot),
        is_certified=bool(project.is_certified),
        marketing_consent=bool(project.marketing_consent),
        marketing_consent_at=project.marketing_consent_at,
        status_changed_at=project.status_changed_at,
        created_at=project.created_at,
        updated_at=project.updated_at,
        assigned_contractor_id=str(project.assigned_contractor_id) if project.assigned_contractor_id else None,
        assigned_expert_id=str(project.assigned_expert_id) if project.assigned_expert_id else None,
        scheduled_for=project.scheduled_for,
    )


def _project_client_id(project: Project) -> Optional[str]:
    if not isinstance(project.client_info, dict):
        return None
    client_id = (
        project.client_info.get("client_id") or project.client_info.get("user_id") or project.client_info.get("id")
    )
    return str(client_id) if client_id else None


def _ensure_project_access(
    project: Project,
    current_user: CurrentUser,
    *,
    allow_admin: bool = False,
    allow_client: bool = False,
    allow_contractor: bool = False,
    allow_expert: bool = False,
) -> None:
    role = current_user.role
    if role == "ADMIN" and allow_admin:
        return
    if role == "CLIENT" and allow_client:
        if _project_client_id(project) == current_user.id:
            return
        raise HTTPException(403, "Prieiga uždrausta")
    if role == "SUBCONTRACTOR" and allow_contractor:
        if project.assigned_contractor_id and str(project.assigned_contractor_id) == current_user.id:
            return
        raise HTTPException(403, "Prieiga uždrausta")
    if role == "EXPERT" and allow_expert:
        if project.assigned_expert_id and str(project.assigned_expert_id) == current_user.id:
            return
        raise HTTPException(403, "Prieiga uždrausta")
    raise HTTPException(403, "Prieiga uždrausta")


def _audit_to_out(log: AuditLog) -> AuditLogOut:
    return AuditLogOut(
        id=str(log.id),
        entity_type=log.entity_type,
        entity_id=str(log.entity_id),
        action=log.action,
        old_value=log.old_value,
        new_value=log.new_value,
        actor_type=log.actor_type,
        actor_id=str(log.actor_id) if log.actor_id else None,
        ip_address=str(log.ip_address) if log.ip_address else None,
        user_agent=log.user_agent,
        metadata=log.audit_meta,
        timestamp=log.timestamp,
    )


def _evidence_to_out(ev: Evidence) -> EvidenceOut:
    return EvidenceOut(
        id=str(ev.id),
        project_id=str(ev.project_id),
        file_url=ev.file_url,
        category=ev.category,
        uploaded_by=str(ev.uploaded_by) if ev.uploaded_by else None,
        uploaded_at=ev.uploaded_at,
        created_at=ev.created_at,
        show_on_web=bool(ev.show_on_web),
        is_featured=bool(ev.is_featured),
        location_tag=ev.location_tag,
    )


def _margin_to_out(margin: Margin) -> MarginOut:
    percent = margin.margin_percent
    return MarginOut(
        id=str(margin.id),
        service_type=margin.service_type,
        margin_percent=float(percent) if percent is not None else 0.0,
        valid_from=margin.valid_from,
        valid_until=margin.valid_until,
        created_by=str(margin.created_by) if margin.created_by else None,
        created_at=margin.created_at,
        is_active=margin.valid_until is None,
    )


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(payload: ProjectCreate, request: Request, db: Session = Depends(get_db)):
    project = Project(
        client_info=payload.client_info,
        area_m2=payload.area_m2,
        status=ProjectStatus.DRAFT.value,
    )
    db.add(project)
    db.flush()

    create_audit_log(
        db,
        entity_type="project",
        entity_id=str(project.id),
        action="PROJECT_CREATED",
        old_value=None,
        new_value={"status": project.status},
        actor_type="CLIENT",
        actor_id=None,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    db.commit()
    db.refresh(project)
    return _project_to_out(project)


@router.get("/projects/{project_id}", response_model=ProjectDetail)
async def get_project(
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Projektas nerastas")

    _ensure_project_access(
        project,
        current_user,
        allow_admin=True,
        allow_client=True,
        allow_contractor=True,
        allow_expert=True,
    )

    audit_logs = (
        db.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == "project", AuditLog.entity_id == project.id)
            .order_by(desc(AuditLog.timestamp))
        )
        .scalars()
        .all()
    )
    evidences = db.execute(select(Evidence).where(Evidence.project_id == project.id)).scalars().all()

    return ProjectDetail(
        project=_project_to_out(project),
        audit_logs=[_audit_to_out(log) for log in audit_logs],
        evidences=[_evidence_to_out(ev) for ev in evidences],
    )


@router.get("/client/projects", response_model=ClientProjectListResponse)
async def list_client_projects(
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = None,
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
    db: Session = Depends(get_db),
):
    client_id = current_user.id
    stmt = select(Project).where(
        or_(
            Project.client_info["client_id"].astext == client_id,
            Project.client_info["user_id"].astext == client_id,
            Project.client_info["id"].astext == client_id,
        )
    )

    if cursor:
        cursor_ts, cursor_id = _decode_project_cursor(cursor)
        stmt = stmt.where(
            or_(
                Project.created_at < cursor_ts,
                and_(Project.created_at == cursor_ts, Project.id < cursor_id),
            )
        )

    stmt = stmt.order_by(desc(Project.created_at), desc(Project.id)).limit(limit + 1)
    rows = db.execute(stmt).scalars().all()

    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        if last.created_at:
            next_cursor = _encode_project_cursor(last.created_at, str(last.id))

    return ClientProjectListResponse(
        items=[_project_to_out(project) for project in rows],
        next_cursor=next_cursor,
        has_more=has_more,
    )


def _project_to_admin_out(project: Project) -> AdminProjectOut:
    return AdminProjectOut(
        id=str(project.id),
        status=ProjectStatus(project.status),
        scheduled_for=project.scheduled_for,
        assigned_contractor_id=str(project.assigned_contractor_id) if project.assigned_contractor_id else None,
        assigned_expert_id=str(project.assigned_expert_id) if project.assigned_expert_id else None,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    action: Optional[str] = None,
    actor_type: Optional[str] = None,
    actor_id: Optional[str] = None,
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    role = current_user.role
    if role not in {"ADMIN", "EXPERT", "SUBCONTRACTOR"}:
        raise HTTPException(403, "Prieiga uždrausta")

    stmt = select(AuditLog)

    if role in {"EXPERT", "SUBCONTRACTOR"}:
        if entity_type and entity_type != "project":
            raise HTTPException(403, "Prieiga uždrausta")

        if entity_id:
            try:
                entity_uuid = uuid.UUID(entity_id)
            except ValueError as exc:
                raise HTTPException(400, "Invalid entity_id") from exc
            assigned_project = db.get(Project, entity_uuid)
            if not assigned_project:
                raise HTTPException(403, "Prieiga uždrausta")
            if role == "EXPERT":
                if (
                    not assigned_project.assigned_expert_id
                    or str(assigned_project.assigned_expert_id) != current_user.id
                ):
                    raise HTTPException(403, "Prieiga uždrausta")
            else:
                if (
                    not assigned_project.assigned_contractor_id
                    or str(assigned_project.assigned_contractor_id) != current_user.id
                ):
                    raise HTTPException(403, "Prieiga uždrausta")

        stmt = stmt.join(Project, Project.id == AuditLog.entity_id).where(AuditLog.entity_type == "project")
        if role == "EXPERT":
            stmt = stmt.where(Project.assigned_expert_id == current_user.id)
        else:
            stmt = stmt.where(Project.assigned_contractor_id == current_user.id)

    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)

    if entity_id:
        try:
            entity_uuid = uuid.UUID(entity_id)
        except ValueError as exc:
            raise HTTPException(400, "Invalid entity_id") from exc
        stmt = stmt.where(AuditLog.entity_id == entity_uuid)

    if action:
        stmt = stmt.where(AuditLog.action == action)

    if actor_type:
        stmt = stmt.where(AuditLog.actor_type == actor_type)

    if actor_id:
        try:
            actor_uuid = uuid.UUID(actor_id)
        except ValueError as exc:
            raise HTTPException(400, "Invalid actor_id") from exc
        stmt = stmt.where(AuditLog.actor_id == actor_uuid)

    if from_ts and to_ts and from_ts > to_ts:
        raise HTTPException(400, "from_ts must be <= to_ts")

    if from_ts:
        stmt = stmt.where(AuditLog.timestamp >= from_ts)
    if to_ts:
        stmt = stmt.where(AuditLog.timestamp <= to_ts)

    if cursor:
        cursor_ts, cursor_id = _decode_audit_cursor(cursor)
        stmt = stmt.where(
            or_(
                AuditLog.timestamp < cursor_ts,
                and_(AuditLog.timestamp == cursor_ts, AuditLog.id < cursor_id),
            )
        )

    stmt = stmt.order_by(desc(AuditLog.timestamp), desc(AuditLog.id)).limit(limit + 1)
    rows = db.execute(stmt).scalars().all()

    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        if last.timestamp:
            next_cursor = _encode_audit_cursor(last.timestamp, str(last.id))

    return AuditLogListResponse(
        items=[_audit_to_out(log) for log in rows],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/audit-logs/export")
async def export_audit_logs(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    action: Optional[str] = None,
    actor_type: Optional[str] = None,
    actor_id: Optional[str] = None,
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
    limit: int = Query(10000, ge=1, le=100000),
    cursor: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "ADMIN":
        raise HTTPException(403, "Prieiga uždrausta")

    stmt = select(AuditLog)

    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)

    if entity_id:
        try:
            entity_uuid = uuid.UUID(entity_id)
        except ValueError as exc:
            raise HTTPException(400, "Invalid entity_id") from exc
        stmt = stmt.where(AuditLog.entity_id == entity_uuid)

    if action:
        stmt = stmt.where(AuditLog.action == action)

    if actor_type:
        stmt = stmt.where(AuditLog.actor_type == actor_type)

    if actor_id:
        try:
            actor_uuid = uuid.UUID(actor_id)
        except ValueError as exc:
            raise HTTPException(400, "Invalid actor_id") from exc
        stmt = stmt.where(AuditLog.actor_id == actor_uuid)

    if from_ts and to_ts and from_ts > to_ts:
        raise HTTPException(400, "from_ts must be <= to_ts")

    if from_ts:
        stmt = stmt.where(AuditLog.timestamp >= from_ts)
    if to_ts:
        stmt = stmt.where(AuditLog.timestamp <= to_ts)

    if cursor:
        cursor_ts, cursor_id = _decode_audit_cursor(cursor)
        stmt = stmt.where(
            or_(
                AuditLog.timestamp < cursor_ts,
                and_(AuditLog.timestamp == cursor_ts, AuditLog.id < cursor_id),
            )
        )

    stmt = stmt.order_by(desc(AuditLog.timestamp), desc(AuditLog.id)).limit(limit + 1)
    rows = db.execute(stmt).scalars().all()

    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        if last.timestamp:
            next_cursor = _encode_audit_cursor(last.timestamp, str(last.id))

    def _json_field(value) -> str:
        if value is None:
            return ""
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)

    def _ts_to_iso(value: Optional[datetime]) -> str:
        if not value:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    def generate():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "timestamp",
                "entity_type",
                "entity_id",
                "action",
                "actor_type",
                "actor_id",
                "ip_address",
                "user_agent",
                "old_value",
                "new_value",
                "metadata",
            ]
        )
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)

        for log in rows:
            writer.writerow(
                [
                    _ts_to_iso(log.timestamp),
                    log.entity_type,
                    str(log.entity_id),
                    log.action,
                    log.actor_type,
                    str(log.actor_id) if log.actor_id else "",
                    str(log.ip_address) if log.ip_address else "",
                    log.user_agent or "",
                    _json_field(log.old_value),
                    _json_field(log.new_value),
                    _json_field(log.audit_meta),
                ]
            )
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    headers = {
        "X-Has-More": "true" if has_more else "false",
    }
    if next_cursor:
        headers["X-Next-Cursor"] = next_cursor

    return StreamingResponse(generate(), media_type="text/csv", headers=headers)


@router.get("/admin/token")
async def admin_token(request: Request):
    settings = get_settings()
    if not settings.admin_token_endpoint_enabled:
        raise HTTPException(404, "Nerastas")
    if not settings.supabase_jwt_secret:
        raise HTTPException(500, "Nesukonfigūruotas SUPABASE_JWT_SECRET")

    now = int(time.time())
    ttl_hours = settings.admin_token_ttl_hours if settings.admin_token_ttl_hours > 0 else 1
    exp = now + int(ttl_hours) * 3600
    payload = {
        "sub": settings.admin_token_sub,
        "email": settings.admin_token_email,
        "app_metadata": {"role": "ADMIN"},
        "aud": settings.supabase_jwt_audience,
        "iat": now,
        "exp": exp,
    }
    token = jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")
    return {"token": token, "expires_at": exp}


@router.get("/admin/projects/{project_id}/client-token")
async def admin_client_token(
    project_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.supabase_jwt_secret:
        raise HTTPException(500, "Nesukonfigūruotas SUPABASE_JWT_SECRET")

    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Projektas nerastas")

    client_id = None
    client_email = None
    if isinstance(project.client_info, dict):
        client_id = (
            project.client_info.get("client_id") or project.client_info.get("user_id") or project.client_info.get("id")
        )
        client_email = project.client_info.get("email")

    if not client_id:
        raise HTTPException(400, "client_id missing in project.client_info")

    now = int(time.time())
    ttl_hours = settings.client_token_ttl_hours if settings.client_token_ttl_hours > 0 else 24
    exp = now + int(ttl_hours) * 3600
    payload = {
        "sub": str(client_id),
        "email": client_email or "client@vejapro.local",
        "app_metadata": {"role": "CLIENT"},
        "aud": settings.supabase_jwt_audience,
        "iat": now,
        "exp": exp,
    }
    token = jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")

    create_audit_log(
        db,
        entity_type="project",
        entity_id=str(project.id),
        action="CLIENT_TOKEN_ISSUED",
        old_value=None,
        new_value={"client_id": str(client_id), "ttl_hours": ttl_hours},
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    db.commit()

    return {"token": token, "expires_at": exp, "client_id": str(client_id)}


@router.get("/admin/users/{user_id}/contractor-token")
async def admin_contractor_token(
    user_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.supabase_jwt_secret:
        raise HTTPException(500, "Nesukonfigūruotas SUPABASE_JWT_SECRET")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Vartotojas nerastas")
    if user.role != "SUBCONTRACTOR":
        raise HTTPException(400, "User role must be SUBCONTRACTOR")

    now = int(time.time())
    ttl_hours = 168  # 7 days
    exp = now + ttl_hours * 3600
    payload = {
        "sub": str(user.id),
        "email": user.email or f"contractor-{user.id}@vejapro.local",
        "app_metadata": {"role": "SUBCONTRACTOR"},
        "aud": settings.supabase_jwt_audience,
        "iat": now,
        "exp": exp,
    }
    token = jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")

    create_audit_log(
        db,
        entity_type="user",
        entity_id=str(user.id),
        action="CONTRACTOR_TOKEN_ISSUED",
        old_value=None,
        new_value={"user_id": str(user.id), "ttl_hours": ttl_hours},
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    db.commit()

    return {"token": token, "expires_at": exp, "user_id": str(user.id)}


@router.get("/admin/users/{user_id}/expert-token")
async def admin_expert_token(
    user_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.supabase_jwt_secret:
        raise HTTPException(500, "Nesukonfigūruotas SUPABASE_JWT_SECRET")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Vartotojas nerastas")
    if user.role != "EXPERT":
        raise HTTPException(400, "User role must be EXPERT")

    now = int(time.time())
    ttl_hours = 168  # 7 days
    exp = now + ttl_hours * 3600
    payload = {
        "sub": str(user.id),
        "email": user.email or f"expert-{user.id}@vejapro.local",
        "app_metadata": {"role": "EXPERT"},
        "aud": settings.supabase_jwt_audience,
        "iat": now,
        "exp": exp,
    }
    token = jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")

    create_audit_log(
        db,
        entity_type="user",
        entity_id=str(user.id),
        action="EXPERT_TOKEN_ISSUED",
        old_value=None,
        new_value={"user_id": str(user.id), "ttl_hours": ttl_hours},
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    db.commit()

    return {"token": token, "expires_at": exp, "user_id": str(user.id)}


@router.get("/contractor/projects", response_model=AdminProjectListResponse)
async def list_contractor_projects(
    status: Optional[ProjectStatus] = None,
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = None,
    current_user: CurrentUser = Depends(require_roles("SUBCONTRACTOR")),
    db: Session = Depends(get_db),
):
    stmt = select(Project).where(Project.assigned_contractor_id == current_user.id)

    if status:
        stmt = stmt.where(Project.status == status.value)

    if cursor:
        cursor_ts, cursor_id = _decode_project_cursor(cursor)
        stmt = stmt.where(
            or_(
                Project.created_at < cursor_ts,
                and_(Project.created_at == cursor_ts, Project.id < cursor_id),
            )
        )

    stmt = stmt.order_by(desc(Project.created_at), desc(Project.id)).limit(limit + 1)
    rows = list(db.execute(stmt).scalars())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    items = [
        AdminProjectOut(
            id=str(p.id),
            status=ProjectStatus(p.status),
            scheduled_for=p.scheduled_for,
            assigned_contractor_id=str(p.assigned_contractor_id) if p.assigned_contractor_id else None,
            assigned_expert_id=str(p.assigned_expert_id) if p.assigned_expert_id else None,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in rows
    ]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = _encode_project_cursor(last.created_at, last.id)

    return AdminProjectListResponse(items=items, next_cursor=next_cursor, has_more=has_more)


@router.get("/expert/projects", response_model=AdminProjectListResponse)
async def list_expert_projects(
    status: Optional[ProjectStatus] = None,
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = None,
    current_user: CurrentUser = Depends(require_roles("EXPERT")),
    db: Session = Depends(get_db),
):
    stmt = select(Project).where(Project.assigned_expert_id == current_user.id)

    if status:
        stmt = stmt.where(Project.status == status.value)

    if cursor:
        cursor_ts, cursor_id = _decode_project_cursor(cursor)
        stmt = stmt.where(
            or_(
                Project.created_at < cursor_ts,
                and_(Project.created_at == cursor_ts, Project.id < cursor_id),
            )
        )

    stmt = stmt.order_by(desc(Project.created_at), desc(Project.id)).limit(limit + 1)
    rows = list(db.execute(stmt).scalars())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    items = [
        AdminProjectOut(
            id=str(p.id),
            status=ProjectStatus(p.status),
            scheduled_for=p.scheduled_for,
            assigned_contractor_id=str(p.assigned_contractor_id) if p.assigned_contractor_id else None,
            assigned_expert_id=str(p.assigned_expert_id) if p.assigned_expert_id else None,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in rows
    ]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = _encode_project_cursor(last.created_at, last.id)

    return AdminProjectListResponse(items=items, next_cursor=next_cursor, has_more=has_more)


@router.post("/admin/projects/{project_id}/payment-link", response_model=PaymentLinkResponse)
async def create_payment_link(
    project_id: str,
    payload: PaymentLinkRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
):
    settings = get_settings()
    if not settings.enable_stripe:
        raise HTTPException(404, "Nerastas")
    if not settings.stripe_secret_key:
        raise HTTPException(500, "Nesukonfigūruotas Stripe")

    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Projektas nerastas")

    payment_type = (
        payload.payment_type.value
        if isinstance(payload.payment_type, PaymentType)
        else str(payload.payment_type).upper()
    )
    if payment_type == PaymentType.DEPOSIT.value and project.status != ProjectStatus.DRAFT.value:
        raise HTTPException(400, "Deposit allowed only for DRAFT projects")
    if payment_type == PaymentType.FINAL.value and project.status not in {
        ProjectStatus.CERTIFIED.value,
        ProjectStatus.ACTIVE.value,
    }:
        raise HTTPException(400, "Final payment allowed only for CERTIFIED/ACTIVE projects")
    currency = (payload.currency or "EUR").upper()
    amount_raw = Decimal(str(payload.amount))
    if amount_raw <= 0:
        raise HTTPException(400, "Amount must be greater than 0")
    amount = amount_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    unit_amount = int(amount * 100)
    if unit_amount <= 0:
        raise HTTPException(400, "Invalid amount")

    base_url = str(request.base_url).rstrip("/")
    success_url = payload.success_url or f"{base_url}/?payment=success"
    cancel_url = payload.cancel_url or f"{base_url}/?payment=cancel"

    client_email = None
    client_name = None
    if isinstance(project.client_info, dict):
        client_email = project.client_info.get("email")
        client_name = project.client_info.get("name") or project.client_info.get("client_name")

    description = payload.description or f"VejaPRO {payment_type} payment"
    if client_name:
        description = f"{description} - {client_name}"

    stripe.api_key = settings.stripe_secret_key
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            payment_method_types=["card"],
            customer_email=client_email,
            client_reference_id=str(project.id),
            line_items=[
                {
                    "price_data": {
                        "currency": currency.lower(),
                        "unit_amount": unit_amount,
                        "product_data": {"name": description},
                    },
                    "quantity": 1,
                }
            ],
            payment_intent_data={
                "metadata": {
                    "project_id": str(project.id),
                    "payment_type": payment_type,
                }
            },
            metadata={
                "project_id": str(project.id),
                "payment_type": payment_type,
            },
        )
    except stripe.error.StripeError as exc:
        raise HTTPException(502, "Stripe klaida") from exc

    create_audit_log(
        db,
        entity_type="project",
        entity_id=str(project.id),
        action="PAYMENT_LINK_CREATED",
        old_value=None,
        new_value={
            "payment_type": payment_type,
            "amount": float(amount),
            "currency": currency,
            "session_id": session.get("id"),
        },
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={
            "success_url": success_url,
            "cancel_url": cancel_url,
        },
    )
    db.commit()

    return PaymentLinkResponse(
        url=session.get("url"),
        session_id=session.get("id"),
        amount=float(amount),
        currency=currency,
        payment_type=PaymentType(payment_type),
        expires_at=session.get("expires_at"),
    )


@router.post("/projects/{project_id}/payments/manual", response_model=ManualPaymentResponse, status_code=201)
async def record_manual_payment(
    project_id: str,
    payload: ManualPaymentRequest,
    request: Request,
    response: Response,
    current_user: CurrentUser = Depends(require_roles("SUBCONTRACTOR", "EXPERT", "ADMIN")),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.enable_manual_payments:
        raise HTTPException(404, "Nerastas")

    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Projektas nerastas")

    _ensure_project_access(
        project,
        current_user,
        allow_admin=True,
        allow_contractor=True,
        allow_expert=True,
    )

    payment_type = payload.payment_type.value
    if payment_type == PaymentType.DEPOSIT.value and project.status != ProjectStatus.DRAFT.value:
        raise HTTPException(400, "Deposit allowed only for DRAFT projects")
    if payment_type == PaymentType.FINAL.value and project.status not in {
        ProjectStatus.CERTIFIED.value,
        ProjectStatus.ACTIVE.value,
    }:
        raise HTTPException(400, "Final payment allowed only for CERTIFIED/ACTIVE projects")

    existing = (
        db.query(Payment)
        .filter(
            Payment.provider == "manual",
            Payment.provider_event_id == payload.provider_event_id,
        )
        .first()
    )
    if existing:
        response.status_code = 200
        return ManualPaymentResponse(
            success=True,
            idempotent=True,
            payment_id=str(existing.id),
            provider=existing.provider,
            status=existing.status,
            payment_type=PaymentType(existing.payment_type),
            amount=float(existing.amount),
            currency=existing.currency,
        )

    amount_raw = Decimal(str(payload.amount))
    if amount_raw <= 0:
        raise HTTPException(400, "Amount must be greater than 0")
    amount = amount_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    now = datetime.now(timezone.utc)
    received_at = payload.received_at or now

    payment = Payment(
        project_id=project.id,
        provider="manual",
        provider_intent_id=None,
        provider_event_id=payload.provider_event_id,
        amount=amount,
        currency=payload.currency,
        payment_type=payment_type,
        status="SUCCEEDED",
        raw_payload={"notes": payload.notes} if payload.notes else None,
        payment_method=payload.payment_method,
        received_at=received_at,
        collected_by=_user_fk_or_none(db, current_user.id),
        collection_context=payload.collection_context,
        receipt_no=payload.receipt_no,
        proof_url=payload.proof_url,
        is_manual_confirmed=True,
        confirmed_by=_user_fk_or_none(db, current_user.id),
        confirmed_at=now,
    )
    db.add(payment)
    db.flush()

    create_audit_log(
        db,
        entity_type="payment",
        entity_id=str(payment.id),
        action="PAYMENT_RECORDED_MANUAL",
        old_value=None,
        new_value={
            "project_id": str(project.id),
            "payment_type": payment_type,
            "amount": float(amount),
            "currency": payload.currency,
            "payment_method": payload.payment_method,
            "provider_event_id": payload.provider_event_id,
        },
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={
            "received_at": received_at.isoformat(),
            "collection_context": payload.collection_context,
            "receipt_no": payload.receipt_no,
            "proof_url": payload.proof_url,
        },
    )

    if payment_type == PaymentType.FINAL.value and project.status == ProjectStatus.CERTIFIED.value:
        token = create_sms_confirmation(db, str(project.id))
        create_audit_log(
            db,
            entity_type="project",
            entity_id=str(project.id),
            action="SMS_CONFIRMATION_CREATED",
            old_value=None,
            new_value={"token_hint": token[:4]},
            actor_type=current_user.role,
            actor_id=current_user.id,
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )

        if settings.enable_twilio:
            phone = None
            if isinstance(project.client_info, dict):
                phone = (
                    project.client_info.get("phone")
                    or project.client_info.get("phone_number")
                    or project.client_info.get("tel")
                )
            if phone:
                try:
                    send_sms(phone, f"TAIP {token}")
                    create_audit_log(
                        db,
                        entity_type="project",
                        entity_id=str(project.id),
                        action="SMS_SENT",
                        old_value=None,
                        new_value={"to": phone},
                        actor_type=current_user.role,
                        actor_id=current_user.id,
                        ip_address=_client_ip(request),
                        user_agent=_user_agent(request),
                    )
                except Exception as exc:
                    create_audit_log(
                        db,
                        entity_type="project",
                        entity_id=str(project.id),
                        action="SMS_SEND_FAILED",
                        old_value=None,
                        new_value={"to": phone},
                        actor_type=current_user.role,
                        actor_id=current_user.id,
                        ip_address=_client_ip(request),
                        user_agent=_user_agent(request),
                        metadata={"error": str(exc)},
                    )
            else:
                create_audit_log(
                    db,
                    entity_type="project",
                    entity_id=str(project.id),
                    action="SMS_SEND_FAILED",
                    old_value=None,
                    new_value={"to": None},
                    actor_type=current_user.role,
                    actor_id=current_user.id,
                    ip_address=_client_ip(request),
                    user_agent=_user_agent(request),
                    metadata={"error": "missing_phone"},
                )

    db.commit()
    return ManualPaymentResponse(
        success=True,
        idempotent=False,
        payment_id=str(payment.id),
        provider=payment.provider,
        status=payment.status,
        payment_type=payload.payment_type,
        amount=float(amount),
        currency=payload.currency,
    )


@router.get("/admin/projects", response_model=AdminProjectListResponse)
async def list_admin_projects(
    status: Optional[ProjectStatus] = None,
    assigned_contractor_id: Optional[str] = None,
    assigned_expert_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "ADMIN":
        raise HTTPException(403, "Prieiga uždrausta")

    stmt = select(Project)

    if status:
        stmt = stmt.where(Project.status == status.value)

    if assigned_contractor_id:
        try:
            contractor_uuid = uuid.UUID(assigned_contractor_id)
        except ValueError as exc:
            raise HTTPException(400, "Invalid assigned_contractor_id") from exc
        stmt = stmt.where(Project.assigned_contractor_id == contractor_uuid)

    if assigned_expert_id:
        try:
            expert_uuid = uuid.UUID(assigned_expert_id)
        except ValueError as exc:
            raise HTTPException(400, "Invalid assigned_expert_id") from exc
        stmt = stmt.where(Project.assigned_expert_id == expert_uuid)

    if cursor:
        cursor_ts, cursor_id = _decode_project_cursor(cursor)
        stmt = stmt.where(
            or_(
                Project.created_at < cursor_ts,
                and_(Project.created_at == cursor_ts, Project.id < cursor_id),
            )
        )

    stmt = stmt.order_by(desc(Project.created_at), desc(Project.id)).limit(limit + 1)
    rows = db.execute(stmt).scalars().all()

    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        if last.created_at:
            next_cursor = _encode_project_cursor(last.created_at, str(last.id))

    return AdminProjectListResponse(
        items=[_project_to_admin_out(project) for project in rows],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/admin/margins", response_model=MarginListResponse)
async def list_margins(
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    rows = db.execute(select(Margin).order_by(desc(Margin.created_at), desc(Margin.id))).scalars().all()
    return MarginListResponse(items=[_margin_to_out(margin) for margin in rows])


@router.post("/admin/margins", response_model=MarginOut)
async def create_margin(
    payload: MarginCreateRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    active = (
        db.execute(
            select(Margin)
            .where(
                Margin.service_type == payload.service_type,
                Margin.valid_until.is_(None),
            )
            .with_for_update()
        )
        .scalars()
        .first()
    )
    if active:
        active.valid_until = now

    creator_id = None
    try:
        creator_id = uuid.UUID(current_user.id)
    except ValueError:
        creator_id = None

    margin = Margin(
        service_type=payload.service_type,
        margin_percent=payload.margin_percent,
        valid_from=now,
        valid_until=None,
        created_by=creator_id,
        created_at=now,
    )
    db.add(margin)
    db.flush()

    new_value = {
        "id": str(margin.id),
        "service_type": margin.service_type,
        "margin_percent": float(payload.margin_percent),
        "valid_from": now.isoformat(),
        "valid_until": None,
        "created_by": str(creator_id) if creator_id else None,
        "created_at": now.isoformat(),
    }

    create_audit_log(
        db,
        entity_type="margin",
        entity_id=str(margin.id),
        action="ADMIN_MARGIN_CREATED",
        old_value=None,
        new_value=new_value,
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )

    db.commit()
    db.refresh(margin)
    return _margin_to_out(margin)


@router.post("/admin/projects/{project_id}/assign-contractor")
async def assign_contractor(
    project_id: str,
    payload: AssignRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "ADMIN":
        raise HTTPException(403, "Prieiga uždrausta")

    project = db.execute(select(Project).where(Project.id == project_id).with_for_update()).scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Projektas nerastas")

    try:
        assignee_id = uuid.UUID(payload.user_id)
    except ValueError as exc:
        raise HTTPException(400, "Invalid user_id") from exc

    user = db.get(User, assignee_id)
    if not user:
        raise HTTPException(404, "Vartotojas nerastas")
    if user.role != "SUBCONTRACTOR":
        raise HTTPException(400, "User role must be SUBCONTRACTOR")

    current_assigned = project.assigned_contractor_id
    if current_assigned and str(current_assigned) == str(assignee_id):
        return {"success": True, "no_change": True}

    project.assigned_contractor_id = assignee_id
    create_audit_log(
        db,
        entity_type="project",
        entity_id=str(project.id),
        action="ASSIGN_CONTRACTOR",
        old_value={"assigned_contractor_id": str(current_assigned) if current_assigned else None},
        new_value={"assigned_contractor_id": str(assignee_id)},
        actor_type="ADMIN",
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    db.commit()
    return {"success": True, "no_change": False}


@router.post("/admin/projects/{project_id}/assign-expert")
async def assign_expert(
    project_id: str,
    payload: AssignRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "ADMIN":
        raise HTTPException(403, "Prieiga uždrausta")

    project = db.execute(select(Project).where(Project.id == project_id).with_for_update()).scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Projektas nerastas")

    try:
        assignee_id = uuid.UUID(payload.user_id)
    except ValueError as exc:
        raise HTTPException(400, "Invalid user_id") from exc

    user = db.get(User, assignee_id)
    if not user:
        raise HTTPException(404, "Vartotojas nerastas")
    if user.role != "EXPERT":
        raise HTTPException(400, "User role must be EXPERT")

    current_assigned = project.assigned_expert_id
    if current_assigned and str(current_assigned) == str(assignee_id):
        return {"success": True, "no_change": True}

    project.assigned_expert_id = assignee_id
    create_audit_log(
        db,
        entity_type="project",
        entity_id=str(project.id),
        action="ASSIGN_EXPERT",
        old_value={"assigned_expert_id": str(current_assigned) if current_assigned else None},
        new_value={"assigned_expert_id": str(assignee_id)},
        actor_type="ADMIN",
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    db.commit()
    return {"success": True, "no_change": False}


@router.post("/admin/projects/{project_id}/seed-cert-photos")
async def seed_cert_photos(
    project_id: str,
    request: Request,
    payload: dict = Body(default={}),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "ADMIN":
        raise HTTPException(403, "Prieiga uždrausta")

    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Projektas nerastas")

    count = payload.get("count", 3) if isinstance(payload, dict) else 3
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 3
    count = max(1, min(count, 10))

    uploader_id = None
    try:
        uploader_id = uuid.UUID(current_user.id)
    except (TypeError, ValueError):
        uploader_id = None

    now = datetime.now(timezone.utc)
    created = 0
    for idx in range(count):
        url = f"https://example.com/cert_photo_{idx + 1}.jpg"
        db.add(
            Evidence(
                project_id=project.id,
                file_url=url,
                category=EvidenceCategory.EXPERT_CERTIFICATION.value,
                uploaded_by=uploader_id,
                uploaded_at=now,
                created_at=now,
                show_on_web=False,
                is_featured=False,
            )
        )
        created += 1

    create_audit_log(
        db,
        entity_type="project",
        entity_id=str(project.id),
        action="EVIDENCE_SEEDED",
        old_value=None,
        new_value={"count": created, "category": EvidenceCategory.EXPERT_CERTIFICATION.value},
        actor_type="ADMIN",
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    db.commit()
    return {"success": True, "created": created}


@router.post("/transition-status", response_model=ProjectOut)
async def transition_status(
    payload: TransitionRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.get(Project, payload.project_id)
    if not project:
        raise HTTPException(404, "Projektas nerastas")

    _ensure_project_access(
        project,
        current_user,
        allow_admin=True,
        allow_contractor=True,
        allow_expert=True,
    )

    if payload.actor and current_user.role != "ADMIN":
        raise HTTPException(403, "Prieiga uždrausta")

    actor_type = current_user.role
    if payload.actor and current_user.role == "ADMIN":
        actor_type = payload.actor.strip().upper()
        if actor_type not in ALLOWED_ACTOR_OVERRIDES:
            raise HTTPException(400, "Invalid actor")
    changed = apply_transition(
        db,
        project=project,
        new_status=payload.new_status,
        actor_type=actor_type,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    if changed:
        db.commit()
        db.refresh(project)

    return _project_to_out(project)


@router.post("/upload-evidence", response_model=UploadEvidenceResponse)
async def upload_evidence(
    request: Request,
    project_id: str = Form(...),
    category: EvidenceCategory = Form(...),
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_roles("SUBCONTRACTOR", "EXPERT")),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Projektas nerastas")

    _ensure_project_access(
        project,
        current_user,
        allow_contractor=True,
        allow_expert=True,
    )

    if current_user.role == "SUBCONTRACTOR" and category == EvidenceCategory.EXPERT_CERTIFICATION:
        raise HTTPException(403, "Prieiga uždrausta")
    if current_user.role == "EXPERT" and category != EvidenceCategory.EXPERT_CERTIFICATION:
        raise HTTPException(403, "Prieiga uždrausta")

    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")
    if len(content) > MAX_EVIDENCE_FILE_BYTES:
        raise HTTPException(413, "File is too large")

    _, file_url = upload_evidence_file(
        project_id=project_id,
        filename=file.filename,
        content=content,
        content_type=file.content_type,
    )

    evidence = Evidence(
        project_id=project.id,
        file_url=file_url,
        category=category.value,
        uploaded_by=current_user.id,
    )
    db.add(evidence)
    db.flush()

    if settings.enable_vision_ai and category == EvidenceCategory.SITE_BEFORE:
        project.vision_analysis = analyze_site_photo(file_url)

    create_audit_log(
        db,
        entity_type="evidence",
        entity_id=str(evidence.id),
        action="UPLOAD_EVIDENCE",
        old_value=None,
        new_value={"file_url": file_url, "category": category.value},
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    db.commit()

    return UploadEvidenceResponse(
        evidence_id=str(evidence.id),
        file_url=file_url,
        category=category,
    )


@router.post("/certify-project", response_model=CertifyResponse)
async def certify_project(
    payload: CertifyRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("EXPERT", "ADMIN")),
    db: Session = Depends(get_db),
):
    project = db.get(Project, payload.project_id)
    if not project:
        raise HTTPException(404, "Projektas nerastas")

    _ensure_project_access(
        project,
        current_user,
        allow_admin=True,
        allow_expert=True,
    )

    if project.status != ProjectStatus.PENDING_EXPERT.value:
        raise HTTPException(400, "Projektas dar neparuotas sertifikavimui")

    evidence_count = db.execute(
        select(func.count())
        .select_from(Evidence)
        .where(
            Evidence.project_id == project.id,
            Evidence.category == EvidenceCategory.EXPERT_CERTIFICATION.value,
        )
    ).scalar()
    if evidence_count < 3:
        raise HTTPException(400, f"Reikia mažiausiai 3 sertifikavimo nuotraukų. Rasta: {evidence_count}.")

    changed = apply_transition(
        db,
        project=project,
        new_status=ProjectStatus.CERTIFIED,
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={"checklist": payload.checklist, "notes": payload.notes},
    )
    if changed:
        create_audit_log(
            db,
            entity_type="project",
            entity_id=str(project.id),
            action="CERTIFY_PROJECT",
            old_value=None,
            new_value={"status": ProjectStatus.CERTIFIED.value},
            actor_type=current_user.role,
            actor_id=current_user.id,
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )
        db.commit()
        db.refresh(project)

    return CertifyResponse(
        success=True,
        project_status=ProjectStatus(project.status),
        certificate_ready=False,
    )


@router.get("/projects/{project_id}/certificate")
async def get_certificate(
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Projektas nerastas")

    _ensure_project_access(
        project,
        current_user,
        allow_admin=True,
        allow_client=True,
        allow_contractor=True,
        allow_expert=True,
    )

    if project.status not in [ProjectStatus.CERTIFIED.value, ProjectStatus.ACTIVE.value]:
        raise HTTPException(400, "Projektas nėra sertifikuotas")

    client_name = None
    if isinstance(project.client_info, dict):
        client_name = project.client_info.get("name") or project.client_info.get("client_name")

    pdf_bytes = generate_certificate_pdf(
        {
            "project_id": str(project.id),
            "client_name": client_name or "Client",
            "certified_at": project.status_changed_at,
            "area_m2": project.area_m2,
        }
    )

    filename = f"certificate_{project.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"},
    )


@router.post("/projects/{project_id}/marketing-consent", response_model=MarketingConsentOut)
async def update_marketing_consent(
    project_id: str,
    request: Request,
    payload: MarketingConsentRequest = Body(default=MarketingConsentRequest()),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Projektas nerastas")

    _ensure_project_access(
        project,
        current_user,
        allow_admin=True,
        allow_client=True,
    )

    old_value = bool(project.marketing_consent)
    project.marketing_consent = payload.consent
    project.marketing_consent_at = datetime.now(timezone.utc) if payload.consent else None

    create_audit_log(
        db,
        entity_type="project",
        entity_id=str(project.id),
        action="MARKETING_CONSENT_UPDATE",
        old_value={"marketing_consent": old_value},
        new_value={"marketing_consent": payload.consent},
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )

    if not payload.consent:
        unpublish_project_evidences(
            db,
            project_id=str(project.id),
            actor_type=current_user.role,
            actor_id=current_user.id,
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )

    db.commit()
    db.refresh(project)

    return MarketingConsentOut(
        success=True,
        marketing_consent=bool(project.marketing_consent),
        marketing_consent_at=project.marketing_consent_at,
    )


@router.post("/evidences/{evidence_id}/approve-for-web")
async def approve_evidence_for_web(
    evidence_id: str,
    request: Request,
    payload: ApproveEvidenceRequest = Body(default=ApproveEvidenceRequest()),
    current_user: CurrentUser = Depends(require_roles("EXPERT", "ADMIN")),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.enable_marketing_module:
        raise HTTPException(404, "Nerastas")

    evidence = db.get(Evidence, evidence_id)
    if not evidence:
        raise HTTPException(404, "Evidence not found")

    project = db.get(Project, evidence.project_id)
    if not project:
        raise HTTPException(404, "Projektas nerastas")

    _ensure_project_access(
        project,
        current_user,
        allow_admin=True,
        allow_expert=True,
    )

    if not project.marketing_consent:
        raise HTTPException(400, "Klientas nesutiko su nuotrauku naudojimu")

    if project.status not in [ProjectStatus.CERTIFIED.value, ProjectStatus.ACTIVE.value]:
        raise HTTPException(400, "Projektas dar nesertifikuotas")

    old_value = {
        "show_on_web": bool(evidence.show_on_web),
        "location_tag": evidence.location_tag,
        "is_featured": bool(evidence.is_featured),
    }

    evidence.show_on_web = True
    if payload.location_tag is not None:
        evidence.location_tag = payload.location_tag
    if payload.is_featured is not None:
        evidence.is_featured = payload.is_featured

    new_value = {
        "show_on_web": bool(evidence.show_on_web),
        "location_tag": evidence.location_tag,
        "is_featured": bool(evidence.is_featured),
    }

    create_audit_log(
        db,
        entity_type="evidence",
        entity_id=str(evidence.id),
        action="EVIDENCE_APPROVED_FOR_WEB",
        old_value=old_value,
        new_value=new_value,
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )

    db.commit()
    return {"success": True}


@router.get("/gallery", response_model=GalleryResponse)
async def get_gallery(
    limit: int = Query(24, le=60),
    cursor: Optional[str] = Query(None),
    location_tag: Optional[str] = None,
    featured_only: bool = False,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.enable_marketing_module:
        raise HTTPException(404, "Nerastas")

    after = aliased(Evidence)
    before = aliased(Evidence)

    stmt = (
        select(after, before)
        .join(
            before,
            and_(
                before.project_id == after.project_id,
                before.category == "SITE_BEFORE",
                before.show_on_web.is_(True),
            ),
        )
        .join(Project, Project.id == after.project_id)
        .where(
            after.show_on_web.is_(True),
            after.category == "EXPERT_CERTIFICATION",
            Project.marketing_consent.is_(True),
            Project.status.in_([ProjectStatus.CERTIFIED.value, ProjectStatus.ACTIVE.value]),
        )
    )

    if cursor:
        cursor_time = _decode_cursor(cursor)
        stmt = stmt.where(after.uploaded_at < cursor_time)

    if location_tag:
        stmt = stmt.where(after.location_tag == location_tag)

    if featured_only:
        stmt = stmt.where(after.is_featured.is_(True))

    stmt = stmt.order_by(after.uploaded_at.desc()).limit(limit + 1)
    rows = db.execute(stmt).all()

    has_more = len(rows) > limit
    rows = rows[:limit]

    items = [
        GalleryItem(
            id=str(after_ev.id),
            project_id=str(after_ev.project_id),
            before_url=before_ev.file_url,
            after_url=after_ev.file_url,
            location_tag=after_ev.location_tag,
            is_featured=bool(after_ev.is_featured),
            uploaded_at=after_ev.uploaded_at,
        )
        for after_ev, before_ev in rows
    ]

    next_cursor = None
    if has_more and rows:
        next_cursor = _encode_cursor(rows[-1][0].uploaded_at)

    return GalleryResponse(items=items, next_cursor=next_cursor, has_more=has_more)


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    if not settings.enable_stripe:
        raise HTTPException(404, "Nerastas")
    sig_header = request.headers.get("stripe-signature")
    if settings.allow_insecure_webhooks and not sig_header:
        return {"received": True}
    if not settings.stripe_secret_key or not settings.stripe_webhook_secret:
        if settings.allow_insecure_webhooks:
            return {"received": True}
        raise HTTPException(500, "Nesukonfigūruotas Stripe")

    stripe.api_key = settings.stripe_secret_key
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except ValueError as exc:
        raise HTTPException(400, "Invalid payload") from exc
    except stripe.error.SignatureVerificationError as exc:
        raise HTTPException(400, "Invalid signature") from exc

    event_type = event.get("type")
    data_object = event.get("data", {}).get("object", {}) if isinstance(event, dict) else {}
    event_id = event.get("id") if isinstance(event, dict) else None

    if event_type in {"payment_intent.succeeded"}:
        # idempotency check
        if event_id:
            existing = (
                db.query(Payment).filter(Payment.provider == "stripe", Payment.provider_event_id == event_id).first()
            )
            if existing:
                return {"received": True}

        metadata = data_object.get("metadata", {}) or {}
        project_id = metadata.get("project_id")
        payment_type = (metadata.get("payment_type") or "").upper()

        if not project_id:
            raise HTTPException(400, "Missing project_id")

        project = db.get(Project, project_id)
        if not project:
            raise HTTPException(404, "Projektas nerastas")

        payment = Payment(
            project_id=project.id,
            provider="stripe",
            provider_intent_id=data_object.get("id"),
            provider_event_id=event_id,
            amount=(data_object.get("amount_received") or 0) / 100,
            currency=(data_object.get("currency") or "").upper(),
            payment_type=payment_type or "UNKNOWN",
            status="SUCCEEDED",
            raw_payload=data_object,
        )
        db.add(payment)

        if payment_type == "DEPOSIT":
            apply_transition(
                db,
                project=project,
                new_status=ProjectStatus.PAID,
                actor_type="SYSTEM_STRIPE",
                actor_id=None,
                ip_address=_client_ip(request),
                user_agent=_user_agent(request),
            )

        if payment_type == "FINAL":
            if project.status not in [ProjectStatus.CERTIFIED.value, ProjectStatus.ACTIVE.value]:
                raise HTTPException(400, "Projektas dar nesertifikuotas")
            token = create_sms_confirmation(db, str(project.id))
            create_audit_log(
                db,
                entity_type="project",
                entity_id=str(project.id),
                action="SMS_CONFIRMATION_CREATED",
                old_value=None,
                new_value={"token_hint": token[:4]},
                actor_type="SYSTEM_STRIPE",
                actor_id=None,
                ip_address=_client_ip(request),
                user_agent=_user_agent(request),
            )

            phone = None
            if isinstance(project.client_info, dict):
                phone = (
                    project.client_info.get("phone")
                    or project.client_info.get("phone_number")
                    or project.client_info.get("tel")
                )
            if phone:
                try:
                    send_sms(phone, f"TAIP {token}")
                    create_audit_log(
                        db,
                        entity_type="project",
                        entity_id=str(project.id),
                        action="SMS_SENT",
                        old_value=None,
                        new_value={"to": phone},
                        actor_type="SYSTEM_STRIPE",
                        actor_id=None,
                        ip_address=_client_ip(request),
                        user_agent=_user_agent(request),
                    )
                except Exception as exc:
                    create_audit_log(
                        db,
                        entity_type="project",
                        entity_id=str(project.id),
                        action="SMS_SEND_FAILED",
                        old_value=None,
                        new_value={"to": phone},
                        actor_type="SYSTEM_STRIPE",
                        actor_id=None,
                        ip_address=_client_ip(request),
                        user_agent=_user_agent(request),
                        metadata={"error": str(exc)},
                    )
            else:
                create_audit_log(
                    db,
                    entity_type="project",
                    entity_id=str(project.id),
                    action="SMS_SEND_FAILED",
                    old_value=None,
                    new_value={"to": None},
                    actor_type="SYSTEM_STRIPE",
                    actor_id=None,
                    ip_address=_client_ip(request),
                    user_agent=_user_agent(request),
                    metadata={"error": "missing_phone"},
                )

        db.commit()

    return {"received": True}


@router.post("/webhook/twilio")
async def twilio_webhook(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    if not settings.enable_twilio:
        raise HTTPException(404, "Nerastas")
    if not settings.twilio_auth_token:
        raise HTTPException(500, "Nesukonfigūruotas Twilio")

    form = await request.form()
    from_phone = form.get("From")
    ip_address = _client_ip(request)

    if settings.rate_limit_webhook_enabled:
        key = f"twilio:from:{from_phone or 'unknown'}"
        allowed, _ = rate_limiter.allow(key, settings.rate_limit_twilio_from_per_min, 60)
        if not allowed:
            create_audit_log(
                db,
                entity_type="system",
                entity_id=SYSTEM_ENTITY_ID,
                action="RATE_LIMIT_BLOCKED",
                old_value=None,
                new_value=None,
                actor_type="SYSTEM",
                actor_id=None,
                ip_address=ip_address,
                user_agent=_user_agent(request),
                metadata={
                    "path": "/api/v1/webhook/twilio",
                    "key": key,
                    "limit": settings.rate_limit_twilio_from_per_min,
                    "window_seconds": 60,
                },
            )
            db.commit()
            return _twilio_empty_response()

    signature = request.headers.get("X-Twilio-Signature")
    validator = RequestValidator(settings.twilio_auth_token)
    request_url = settings.twilio_webhook_url or _twilio_request_url(request)
    if not signature or not validator.validate(request_url, dict(form), signature):
        create_audit_log(
            db,
            entity_type="system",
            entity_id=SYSTEM_ENTITY_ID,
            action="TWILIO_SIGNATURE_INVALID",
            old_value=None,
            new_value=None,
            actor_type="SYSTEM",
            actor_id=None,
            ip_address=ip_address,
            user_agent=_user_agent(request),
            metadata={"path": "/api/v1/webhook/twilio", "from": from_phone},
        )
        db.commit()
        return _twilio_empty_response()

    body = (form.get("Body") or "").strip().upper()

    match = re.match(r"^TAIP\s+([A-Z0-9_-]{4,})$", body)
    if not match:
        return _twilio_empty_response()

    token = match.group(1)
    confirmation = find_sms_confirmation(db, token)
    if not confirmation:
        create_audit_log(
            db,
            entity_type="system",
            entity_id=SYSTEM_ENTITY_ID,
            action="SMS_CONFIRMATION_INVALID_TOKEN_ATTEMPT",
            old_value=None,
            new_value=None,
            actor_type="SYSTEM_TWILIO",
            actor_id=None,
            ip_address=ip_address,
            user_agent=_user_agent(request),
            metadata={"from": from_phone, "body_len": len(body)},
        )
        db.commit()
        return _twilio_empty_response()

    if confirmation.status != "PENDING":
        return _twilio_empty_response()

    now = datetime.now(timezone.utc)
    if confirmation.attempts >= 3:
        confirmation.status = "FAILED"
        create_audit_log(
            db,
            entity_type="project",
            entity_id=str(confirmation.project_id),
            action="SMS_CONFIRMATION_FAILED",
            old_value=None,
            new_value={"from": from_phone},
            actor_type="CLIENT",
            actor_id=None,
            ip_address=ip_address,
            user_agent=_user_agent(request),
        )
        db.commit()
        return _twilio_empty_response()

    if confirmation.expires_at < now:
        increment_sms_attempt(db, confirmation)
        confirmation.status = "EXPIRED"
        create_audit_log(
            db,
            entity_type="project",
            entity_id=str(confirmation.project_id),
            action="SMS_CONFIRMATION_EXPIRED",
            old_value=None,
            new_value={"from": from_phone},
            actor_type="CLIENT",
            actor_id=None,
            ip_address=ip_address,
            user_agent=_user_agent(request),
        )
        db.commit()
        return _twilio_empty_response()

    project = db.get(Project, confirmation.project_id)
    if not project:
        return _twilio_empty_response()

    if project.status not in [ProjectStatus.CERTIFIED.value, ProjectStatus.ACTIVE.value]:
        create_audit_log(
            db,
            entity_type="project",
            entity_id=str(project.id),
            action="SMS_CONFIRMATION_INVALID_PROJECT_STATUS",
            old_value=None,
            new_value={"status": project.status},
            actor_type="SYSTEM_TWILIO",
            actor_id=None,
            ip_address=ip_address,
            user_agent=_user_agent(request),
            metadata={"from": from_phone},
        )
        db.commit()
        return _twilio_empty_response()

    if not is_final_payment_recorded(db, str(project.id)):
        increment_sms_attempt(db, confirmation)
        create_audit_log(
            db,
            entity_type="project",
            entity_id=str(project.id),
            action="SMS_CONFIRMATION_FINAL_PAYMENT_MISSING",
            old_value=None,
            new_value={"from": from_phone},
            actor_type="CLIENT",
            actor_id=None,
            ip_address=ip_address,
            user_agent=_user_agent(request),
        )
        db.commit()
        return _twilio_empty_response()

    changed = apply_transition(
        db,
        project=project,
        new_status=ProjectStatus.ACTIVE,
        actor_type="SYSTEM_TWILIO",
        actor_id=None,
        ip_address=ip_address,
        user_agent=_user_agent(request),
        metadata={"sms": "confirmed"},
    )
    if changed:
        confirmation.status = "CONFIRMED"
        confirmation.confirmed_at = now
        confirmation.confirmed_from_phone = from_phone

        create_audit_log(
            db,
            entity_type="project",
            entity_id=str(project.id),
            action="SMS_CONFIRMED",
            old_value=None,
            new_value={"status": ProjectStatus.ACTIVE.value},
            actor_type="SYSTEM_TWILIO",
            actor_id=None,
            ip_address=ip_address,
            user_agent=_user_agent(request),
            metadata={"from": from_phone},
        )
        db.commit()

    return _twilio_empty_response()
