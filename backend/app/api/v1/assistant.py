from datetime import datetime, timezone
from typing import Optional
import base64
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, desc, select, or_
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.models.project import CallRequest, Appointment, Project
from app.schemas.assistant import (
    CallRequestCreate,
    CallRequestListResponse,
    CallRequestOut,
    CallRequestStatus,
    CallRequestUpdate,
    AppointmentCreate,
    AppointmentListResponse,
    AppointmentOut,
    AppointmentStatus,
    AppointmentUpdate,
)
from app.services.transition_service import create_audit_log
from app.utils.rate_limit import get_client_ip, get_user_agent


router = APIRouter()
SYSTEM_ENTITY_ID = "00000000-0000-0000-0000-000000000000"


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
        raise HTTPException(400, "Invalid cursor") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed, item_id


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
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _appointment_to_out(row: Appointment) -> AppointmentOut:
    return AppointmentOut(
        id=str(row.id),
        project_id=str(row.project_id) if row.project_id else None,
        call_request_id=str(row.call_request_id) if row.call_request_id else None,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        status=AppointmentStatus(row.status),
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
    settings = get_settings()
    if not settings.enable_call_assistant:
        raise HTTPException(404, "Not found")

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
        actor_type="PUBLIC",
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
    settings = get_settings()
    if not settings.enable_calendar:
        raise HTTPException(404, "Not found")

    if payload.ends_at <= payload.starts_at:
        raise HTTPException(400, "ends_at must be after starts_at")

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

    appointment = Appointment(
        project_id=project_id,
        call_request_id=call_request_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        status=payload.status.value,
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
    appointment = db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(404, "Appointment not found")

    old_value = {
        "status": appointment.status,
        "starts_at": appointment.starts_at.isoformat() if appointment.starts_at else None,
        "ends_at": appointment.ends_at.isoformat() if appointment.ends_at else None,
        "notes": appointment.notes,
    }

    if payload.status is not None:
        appointment.status = payload.status.value
    if payload.starts_at is not None:
        appointment.starts_at = payload.starts_at
    if payload.ends_at is not None:
        appointment.ends_at = payload.ends_at
    if payload.notes is not None:
        appointment.notes = payload.notes

    if appointment.ends_at <= appointment.starts_at:
        raise HTTPException(400, "ends_at must be after starts_at")

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

    db.commit()
    db.refresh(appointment)
    return _appointment_to_out(appointment)
