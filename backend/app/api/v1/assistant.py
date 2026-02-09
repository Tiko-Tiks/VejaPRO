import base64
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.models.project import Appointment, CallRequest, Project, User
from app.schemas.assistant import (
    AppointmentCreate,
    AppointmentListResponse,
    AppointmentOut,
    AppointmentStatus,
    AppointmentUpdate,
    CallRequestCreate,
    CallRequestListResponse,
    CallRequestOut,
    CallRequestStatus,
    CallRequestUpdate,
)
from app.services.transition_service import create_audit_log
from app.utils.rate_limit import get_client_ip, get_user_agent, rate_limiter

router = APIRouter()


def _ensure_call_assistant_enabled() -> None:
    settings = get_settings()
    if not settings.enable_call_assistant:
        raise HTTPException(404, "Nerastas")


def _ensure_calendar_enabled() -> None:
    settings = get_settings()
    if not settings.enable_calendar:
        raise HTTPException(404, "Nerastas")


def _encode_cursor(ts: datetime, item_id: str) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    payload = f"{ts.isoformat()}|{item_id}".encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("utf-8")


def _decode_cursor(value: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(value.encode("utf-8")).decode("utf-8")
        ts_raw, id_raw = raw.split("|", 1)
        parsed = datetime.fromisoformat(ts_raw)
        item_id = uuid.UUID(id_raw)
    except Exception as exc:
        raise HTTPException(400, "Neteisingas žymeklis") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed, item_id


def _sync_project_scheduled_for(db: Session, project_id: str) -> None:
    project = db.get(Project, project_id)
    if not project:
        return

    earliest = db.execute(
        select(func.min(Appointment.starts_at)).where(
            Appointment.project_id == project.id,
            Appointment.status == "CONFIRMED",
            Appointment.visit_type == "PRIMARY",
        )
    ).scalar_one_or_none()
    project.scheduled_for = earliest


def _call_request_to_out(row: CallRequest) -> CallRequestOut:
    return CallRequestOut(
        id=str(row.id),
        name=row.name,
        phone=row.phone,
        email=row.email,
        preferred_time=row.preferred_time,
        notes=row.notes,
        status=CallRequestStatus(row.status),
        source=row.source,
        converted_project_id=str(row.converted_project_id) if row.converted_project_id else None,
        preferred_channel=row.preferred_channel,
        intake_state=row.intake_state if isinstance(row.intake_state, dict) else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _appointment_to_out(row: Appointment) -> AppointmentOut:
    return AppointmentOut(
        id=str(row.id),
        project_id=str(row.project_id) if row.project_id else None,
        call_request_id=str(row.call_request_id) if row.call_request_id else None,
        resource_id=str(row.resource_id) if row.resource_id else None,
        visit_type=row.visit_type,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        status=AppointmentStatus(row.status),
        lock_level=row.lock_level,
        locked_at=row.locked_at,
        locked_by=str(row.locked_by) if row.locked_by else None,
        lock_reason=row.lock_reason,
        hold_expires_at=row.hold_expires_at,
        weather_class=row.weather_class,
        route_date=row.route_date,
        route_sequence=row.route_sequence,
        row_version=row.row_version,
        superseded_by_id=str(row.superseded_by_id) if row.superseded_by_id else None,
        cancelled_at=row.cancelled_at,
        cancelled_by=str(row.cancelled_by) if row.cancelled_by else None,
        cancel_reason=row.cancel_reason,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/call-requests", response_model=CallRequestOut, status_code=201)
async def create_call_request(
    payload: CallRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    _ensure_call_assistant_enabled()

    # Rate limit public call requests: max 10 per minute per IP
    ip = get_client_ip(request) or "unknown"
    allowed, _ = rate_limiter.allow(f"call_request:ip:{ip}", 10, 60)
    if not allowed:
        raise HTTPException(429, "Too Many Requests")

    call_request = CallRequest(
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
        preferred_time=payload.preferred_time,
        notes=payload.notes,
        status=CallRequestStatus.NEW.value,
        source="public",
    )
    db.add(call_request)
    db.flush()

    create_audit_log(
        db,
        entity_type="call_request",
        entity_id=str(call_request.id),
        action="CALL_REQUEST_CREATED",
        old_value=None,
        new_value={"status": call_request.status},
        # Canonical actor types: public request is treated as CLIENT with unknown actor_id.
        actor_type="CLIENT",
        actor_id=None,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )

    db.commit()
    db.refresh(call_request)
    return _call_request_to_out(call_request)


@router.get("/admin/call-requests", response_model=CallRequestListResponse)
async def list_call_requests(
    status: Optional[CallRequestStatus] = None,
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = None,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _ensure_call_assistant_enabled()
    stmt = select(CallRequest)

    if status:
        stmt = stmt.where(CallRequest.status == status.value)

    if cursor:
        cursor_ts, cursor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                CallRequest.created_at < cursor_ts,
                and_(CallRequest.created_at == cursor_ts, CallRequest.id < cursor_id),
            )
        )

    stmt = stmt.order_by(desc(CallRequest.created_at), desc(CallRequest.id)).limit(limit + 1)
    rows = db.execute(stmt).scalars().all()

    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        if last.created_at:
            next_cursor = _encode_cursor(last.created_at, str(last.id))

    return CallRequestListResponse(
        items=[_call_request_to_out(row) for row in rows],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.patch("/admin/call-requests/{call_request_id}", response_model=CallRequestOut)
async def update_call_request(
    call_request_id: str,
    payload: CallRequestUpdate,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _ensure_call_assistant_enabled()
    call_request = db.get(CallRequest, call_request_id)
    if not call_request:
        raise HTTPException(404, "Call request not found")

    old_value = {
        "status": call_request.status,
        "preferred_time": call_request.preferred_time.isoformat() if call_request.preferred_time else None,
        "notes": call_request.notes,
    }

    if payload.status is not None:
        call_request.status = payload.status.value
    if payload.preferred_time is not None:
        call_request.preferred_time = payload.preferred_time
    if payload.notes is not None:
        call_request.notes = payload.notes

    new_value = {
        "status": call_request.status,
        "preferred_time": call_request.preferred_time.isoformat() if call_request.preferred_time else None,
        "notes": call_request.notes,
    }

    create_audit_log(
        db,
        entity_type="call_request",
        entity_id=str(call_request.id),
        action="CALL_REQUEST_UPDATED",
        old_value=old_value,
        new_value=new_value,
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )

    db.commit()
    db.refresh(call_request)
    return _call_request_to_out(call_request)


@router.get("/admin/appointments", response_model=AppointmentListResponse)
async def list_appointments(
    status: Optional[AppointmentStatus] = None,
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = None,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _ensure_calendar_enabled()
    stmt = select(Appointment)

    if status:
        stmt = stmt.where(Appointment.status == status.value)

    if from_ts and to_ts and from_ts > to_ts:
        raise HTTPException(400, "from_ts must be <= to_ts")

    if from_ts:
        stmt = stmt.where(Appointment.starts_at >= from_ts)
    if to_ts:
        stmt = stmt.where(Appointment.starts_at <= to_ts)

    if cursor:
        cursor_ts, cursor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Appointment.starts_at < cursor_ts,
                and_(Appointment.starts_at == cursor_ts, Appointment.id < cursor_id),
            )
        )

    stmt = stmt.order_by(desc(Appointment.starts_at), desc(Appointment.id)).limit(limit + 1)
    rows = db.execute(stmt).scalars().all()

    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        if last.starts_at:
            next_cursor = _encode_cursor(last.starts_at, str(last.id))

    return AppointmentListResponse(
        items=[_appointment_to_out(row) for row in rows],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.post("/admin/appointments", response_model=AppointmentOut, status_code=201)
async def create_appointment(
    payload: AppointmentCreate,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _ensure_calendar_enabled()

    if payload.ends_at <= payload.starts_at:
        raise HTTPException(400, "ends_at must be after starts_at")

    if payload.status == AppointmentStatus.HELD:
        raise HTTPException(400, "HELD vizitai kuriami tik per Hold API")

    project_id = payload.project_id
    call_request_id = payload.call_request_id

    if project_id:
        project = db.get(Project, project_id)
        if not project:
            raise HTTPException(404, "Project not found")

    call_request = None
    if call_request_id:
        call_request = db.get(CallRequest, call_request_id)
        if not call_request:
            raise HTTPException(404, "Call request not found")

    # Admin token may have a fixed `sub` that does not exist in `users`.
    # Always resolve a real resource_id (users.id) so appointments are schedulable.
    settings = get_settings()
    resource_id: uuid.UUID | None = None

    if payload.resource_id:
        try:
            candidate = uuid.UUID(payload.resource_id)
        except ValueError as exc:
            raise HTTPException(400, "Invalid resource_id") from exc
        if not db.get(User, candidate):
            raise HTTPException(404, "Resource user not found")
        resource_id = candidate
    else:
        try:
            current_uuid = uuid.UUID(current_user.id)
        except ValueError:
            current_uuid = None

        if current_uuid and db.get(User, current_uuid):
            resource_id = current_uuid
        else:
            if settings.schedule_default_resource_id:
                try:
                    candidate = uuid.UUID(settings.schedule_default_resource_id)
                except ValueError:
                    candidate = None
                if candidate and db.get(User, candidate):
                    resource_id = candidate

            if resource_id is None:
                resource_id = (
                    db.execute(select(User.id).where(User.is_active.is_(True)).order_by(User.created_at.asc()).limit(1))
                    .scalars()
                    .first()
                )

    if resource_id is None:
        raise HTTPException(400, "resource_id is required (no default resource configured)")

    lock_level = 1 if payload.status == AppointmentStatus.CONFIRMED else 0
    cancelled_at = None
    cancel_reason = None
    cancelled_by = None
    if payload.status == AppointmentStatus.CANCELLED:
        cancelled_at = datetime.now(timezone.utc)
        cancel_reason = "ADMIN_CANCEL"
        cancelled_by = uuid.UUID(current_user.id) if db.get(User, current_user.id) else None

    appointment = Appointment(
        project_id=project_id,
        call_request_id=call_request_id,
        resource_id=resource_id,
        visit_type="PRIMARY",
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        status=payload.status.value,
        lock_level=lock_level,
        weather_class="MIXED",
        route_date=payload.starts_at.date(),
        row_version=1,
        cancelled_at=cancelled_at,
        cancelled_by=cancelled_by,
        cancel_reason=cancel_reason,
        notes=payload.notes,
    )
    db.add(appointment)
    db.flush()

    if call_request and call_request.status != CallRequestStatus.SCHEDULED.value:
        call_request.status = CallRequestStatus.SCHEDULED.value

    create_audit_log(
        db,
        entity_type="appointment",
        entity_id=str(appointment.id),
        action="APPOINTMENT_CREATED",
        old_value=None,
        new_value={
            "project_id": project_id,
            "call_request_id": call_request_id,
            "status": appointment.status,
        },
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )

    if project_id:
        _sync_project_scheduled_for(db, project_id)

    db.commit()
    db.refresh(appointment)
    return _appointment_to_out(appointment)


@router.patch("/admin/appointments/{appointment_id}", response_model=AppointmentOut)
async def update_appointment(
    appointment_id: str,
    payload: AppointmentUpdate,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _ensure_calendar_enabled()
    appointment = db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(404, "Appointment not found")

    if payload.starts_at is not None or payload.ends_at is not None:
        raise HTTPException(
            400,
            "Laiko keitimas draudžiamas. Naudokite RESCHEDULE (preview -> confirm).",
        )

    old_value = {
        "status": appointment.status,
        "starts_at": appointment.starts_at.isoformat() if appointment.starts_at else None,
        "ends_at": appointment.ends_at.isoformat() if appointment.ends_at else None,
        "notes": appointment.notes,
    }

    if payload.status is not None:
        if payload.status != AppointmentStatus.CANCELLED:
            raise HTTPException(400, "Leidžiama tik atšaukti vizitą (CANCELLED).")
        appointment.status = payload.status.value
        appointment.cancelled_at = datetime.now(timezone.utc)
        appointment.cancel_reason = "ADMIN_CANCEL"
        appointment.cancelled_by = uuid.UUID(current_user.id) if db.get(User, current_user.id) else None
    if payload.notes is not None:
        appointment.notes = payload.notes

    new_value = {
        "status": appointment.status,
        "starts_at": appointment.starts_at.isoformat() if appointment.starts_at else None,
        "ends_at": appointment.ends_at.isoformat() if appointment.ends_at else None,
        "notes": appointment.notes,
    }

    create_audit_log(
        db,
        entity_type="appointment",
        entity_id=str(appointment.id),
        action="APPOINTMENT_UPDATED",
        old_value=old_value,
        new_value=new_value,
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )

    appointment.row_version = int(appointment.row_version or 1) + 1
    if appointment.project_id:
        _sync_project_scheduled_for(db, str(appointment.project_id))
    db.commit()
    db.refresh(appointment)
    return _appointment_to_out(appointment)
