from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import asc, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.models.project import (
    Appointment,
    CallRequest,
    ConversationLock,
    Project,
    SchedulePreview,
    User,
)
from app.schemas.schedule import (
    DailyApproveRequest,
    DailyApproveResponse,
    HoldCancelRequest,
    HoldCancelResponse,
    HoldConfirmRequest,
    HoldConfirmResponse,
    HoldCreateRequest,
    HoldCreateResponse,
    HoldExpireResponse,
    RescheduleConfirmRequest,
    RescheduleConfirmResponse,
    ReschedulePreviewRequest,
    ReschedulePreviewResponse,
    RescheduleScope,
    RescheduleSummary,
    SuggestedAction,
)
from app.services.notification_outbox import enqueue_notification
from app.services.transition_service import create_audit_log

router = APIRouter()


def _with_for_update_if_supported(stmt, db: Session):
    # SQLite (CI/tests) does not support `SELECT ... FOR UPDATE`.
    if db.bind is None:
        return stmt
    if db.bind.dialect.name == "sqlite":
        return stmt
    return stmt.with_for_update()


def _now_utc() -> datetime:
    # SQLite (used in CI/tests) stores timezone-aware datetimes as naive values.
    # To avoid naive/aware comparison crashes, use a naive UTC "now" when DB is SQLite.
    settings = get_settings()
    if (settings.database_url or "").startswith("sqlite"):
        # datetime.utcnow() is deprecated; keep the same naive-UTC semantics.
        return datetime.now(timezone.utc).replace(tzinfo=None)
    return datetime.now(timezone.utc)


def _extract_phone_from_client_info(client_info: object) -> str | None:
    if not isinstance(client_info, dict):
        return None
    for key in ["phone", "phone_number", "tel", "telephone", "mobile"]:
        raw = client_info.get(key)
        if raw is None:
            continue
        value = str(raw).strip()
        if value:
            return value
    return None


def _extract_email_from_client_info(client_info: object) -> str | None:
    if not isinstance(client_info, dict):
        return None
    for key in ["email", "email_address", "e_mail"]:
        raw = client_info.get(key)
        if raw is None:
            continue
        value = str(raw).strip()
        if value:
            return value
    return None


def _format_dt_local(dt: datetime) -> str:
    # Deterministic short format; UI can localize later.
    try:
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError, OverflowError):
        # Fallback for timezone conversion or strftime errors
        return dt.isoformat()


def _parse_uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(400, f"Invalid {field_name}") from exc


def _user_fk_or_none(db: Session, user_id: str) -> uuid.UUID | None:
    """
    Some auth tokens (e.g. admin token endpoint) may use a fixed UUID that is not present
    in our internal `users` table. FK columns must therefore be nullable and set only when
    the referenced row exists.
    """
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        return None
    return user_uuid if db.get(User, user_uuid) else None


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _preview_payload(
    route_date: str,
    resource_id: str,
    original_appointment_ids: list[str],
    suggested_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "route_date": route_date,
        "resource_id": resource_id,
        "original_appointment_ids": original_appointment_ids,
        "suggested_actions": suggested_actions,
    }


def _preview_hash(payload: dict[str, Any]) -> str:
    settings = get_settings()
    secret = (
        settings.supabase_jwt_secret
        or settings.database_url
        or settings.schedule_day_namespace_uuid
        or "schedule-preview-fallback"
    )
    return hmac.new(
        secret.encode("utf-8"),
        _canonical_json(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _schedule_day_entity_id(route_date: str, resource_id: str) -> str:
    settings = get_settings()
    try:
        namespace = uuid.UUID(settings.schedule_day_namespace_uuid)
    except ValueError:
        namespace = uuid.UUID("cd487f5c-baca-4d84-b0e8-97f7bfef7248")
    return str(uuid.uuid5(namespace, f"{route_date}:{resource_id}"))


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


@router.post("/admin/schedule/holds", response_model=HoldCreateResponse, status_code=201)
async def hold_create(
    payload: HoldCreateRequest,
    current_user: CurrentUser = Depends(require_roles("SUBCONTRACTOR", "ADMIN")),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.enable_schedule_engine:
        raise HTTPException(404, "Nerastas")

    now = _now_utc()
    expires_at = now + timedelta(minutes=max(1, settings.schedule_hold_duration_minutes))

    resource_uuid = _parse_uuid(payload.resource_id, "resource_id")
    # App-level overlap guard (needed for SQLite tests; in Postgres we also have an exclusion constraint).
    # Rule: resource may not have overlapping HELD or CONFIRMED appointments.
    # Important: do NOT ignore expired HELD here. Expiry is handled by the worker, and Postgres blocks overlap
    # regardless of hold_expires_at until the row is cancelled.
    overlapping = (
        db.execute(
            select(Appointment.id).where(
                Appointment.resource_id == resource_uuid,
                Appointment.status.in_(["HELD", "CONFIRMED"]),
                Appointment.starts_at < payload.ends_at,
                Appointment.ends_at > payload.starts_at,
            )
        )
        .scalars()
        .first()
    )
    if overlapping:
        raise HTTPException(409, "Laikas neprieinamas")

    # Ensure conversation lock uniqueness: if already present and not expired, return 409.
    existing = (
        db.execute(
            select(ConversationLock).where(
                ConversationLock.channel == payload.channel.value,
                ConversationLock.conversation_id == payload.conversation_id,
            )
        )
        .scalars()
        .one_or_none()
    )
    if existing:
        if existing.hold_expires_at and existing.hold_expires_at > now:
            raise HTTPException(409, "Pokalbis jau turi aktyvią rezervaciją")
        # Expired lock: best-effort cleanup before creating a new hold.
        db.execute(delete(ConversationLock).where(ConversationLock.id == existing.id))
        db.commit()

    appt = Appointment(
        project_id=payload.project_id,
        call_request_id=payload.call_request_id,
        resource_id=resource_uuid,
        visit_type=payload.visit_type or "PRIMARY",
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        status="HELD",
        lock_level=0,
        hold_expires_at=expires_at,
        weather_class=payload.weather_class or "MIXED",
        route_date=payload.starts_at.date(),
        row_version=1,
        notes="HOLD",
    )
    db.add(appt)
    db.flush()

    lock = ConversationLock(
        channel=payload.channel.value,
        conversation_id=payload.conversation_id,
        appointment_id=appt.id,
        visit_type=appt.visit_type,
        hold_expires_at=expires_at,
    )
    db.add(lock)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Most likely: no_overlap_per_resource or uniq_conversation_lock
        raise HTTPException(409, "Laikas neprieinamas") from exc

    return HoldCreateResponse(
        appointment_id=str(appt.id),
        hold_expires_at=expires_at,
        status="HELD",
    )


@router.post("/admin/schedule/holds/confirm", response_model=HoldConfirmResponse)
async def hold_confirm(
    payload: HoldConfirmRequest,
    current_user: CurrentUser = Depends(require_roles("SUBCONTRACTOR", "ADMIN")),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.enable_schedule_engine:
        raise HTTPException(404, "Nerastas")

    now = _now_utc()
    lock = (
        db.execute(
            select(ConversationLock).where(
                ConversationLock.channel == payload.channel.value,
                ConversationLock.conversation_id == payload.conversation_id,
            )
        )
        .scalars()
        .one_or_none()
    )
    if not lock:
        raise HTTPException(404, "Rezervacija nerasta")
    if lock.hold_expires_at <= now:
        raise HTTPException(409, "Rezervacija pasibaigė")

    stmt = _with_for_update_if_supported(select(Appointment).where(Appointment.id == lock.appointment_id), db)
    appt = db.execute(stmt).scalars().one_or_none()
    if not appt:
        raise HTTPException(404, "Susitikimas nerastas")
    if appt.visit_type != lock.visit_type:
        raise HTTPException(409, "Rezervacijos vizito tipas nesutampa")
    if appt.status != "HELD":
        raise HTTPException(409, "Susitikimas nėra HELD būsenoje")
    if appt.hold_expires_at is None or appt.hold_expires_at <= now:
        raise HTTPException(409, "Rezervacija pasibaigė")

    appt.status = "CONFIRMED"
    appt.hold_expires_at = None
    appt.lock_level = 1
    appt.locked_at = now
    appt.locked_by = _user_fk_or_none(db, current_user.id)
    appt.lock_reason = "HOLD_CONFIRM"
    appt.row_version = int(appt.row_version or 1) + 1

    db.execute(delete(ConversationLock).where(ConversationLock.id == lock.id))

    create_audit_log(
        db,
        entity_type="appointment",
        entity_id=str(appt.id),
        action="APPOINTMENT_CONFIRMED",
        old_value={"status": "HELD"},
        new_value={
            "status": "CONFIRMED",
            "starts_at": appt.starts_at.isoformat(),
            "ends_at": appt.ends_at.isoformat(),
            "visit_type": appt.visit_type,
        },
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=None,
        user_agent=None,
        metadata={
            "reason": "HOLD_CONFIRM",
            "comment": "",
            "channel": payload.channel.value,
            "conversation_id": payload.conversation_id,
        },
    )

    if appt.project_id and (appt.visit_type or "") == "PRIMARY":
        _sync_project_scheduled_for(db, str(appt.project_id))

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Rezervacijos patvirtinimo konfliktas") from exc

    return HoldConfirmResponse(appointment_id=str(appt.id), status="CONFIRMED")


@router.post("/admin/schedule/holds/cancel", response_model=HoldCancelResponse)
async def hold_cancel(
    payload: HoldCancelRequest,
    current_user: CurrentUser = Depends(require_roles("SUBCONTRACTOR", "ADMIN")),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.enable_schedule_engine:
        raise HTTPException(404, "Nerastas")

    now = _now_utc()
    lock = (
        db.execute(
            select(ConversationLock).where(
                ConversationLock.channel == payload.channel.value,
                ConversationLock.conversation_id == payload.conversation_id,
            )
        )
        .scalars()
        .one_or_none()
    )
    if not lock:
        raise HTTPException(404, "Rezervacija nerasta")

    stmt = _with_for_update_if_supported(select(Appointment).where(Appointment.id == lock.appointment_id), db)
    appt = db.execute(stmt).scalars().one_or_none()
    if not appt:
        raise HTTPException(404, "Susitikimas nerastas")

    old_status = appt.status
    appt.status = "CANCELLED"
    appt.cancelled_at = now
    appt.cancelled_by = _user_fk_or_none(db, current_user.id)
    appt.cancel_reason = "HOLD_CANCELLED"
    appt.hold_expires_at = None
    appt.row_version = int(appt.row_version or 1) + 1

    db.execute(delete(ConversationLock).where(ConversationLock.id == lock.id))

    create_audit_log(
        db,
        entity_type="appointment",
        entity_id=str(appt.id),
        action="APPOINTMENT_CANCELLED",
        old_value={"status": old_status},
        new_value={"status": "CANCELLED"},
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=None,
        user_agent=None,
        metadata={
            "reason": "HOLD_CANCELLED",
            "comment": payload.comment,
            "channel": payload.channel.value,
            "conversation_id": payload.conversation_id,
        },
    )

    if appt.project_id and (appt.visit_type or "") == "PRIMARY":
        _sync_project_scheduled_for(db, str(appt.project_id))

    db.commit()
    return HoldCancelResponse(appointment_id=str(appt.id), status="CANCELLED")


@router.post("/admin/schedule/holds/expire", response_model=HoldExpireResponse)
async def hold_expire(
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.enable_schedule_engine:
        raise HTTPException(404, "Nerastas")

    now = _now_utc()
    stmt = _with_for_update_if_supported(
        select(Appointment).where(
            Appointment.status == "HELD",
            Appointment.hold_expires_at.is_not(None),
            Appointment.hold_expires_at < now,
        ),
        db,
    )
    expired = db.execute(stmt).scalars().all()
    count = 0
    for appt in expired:
        appt.status = "CANCELLED"
        appt.cancel_reason = "HOLD_EXPIRED"
        appt.hold_expires_at = None
        appt.row_version = int(appt.row_version or 1) + 1
        count += 1

    # Best-effort cleanup of expired conversation locks.
    db.execute(delete(ConversationLock).where(ConversationLock.hold_expires_at < now))
    db.commit()

    return HoldExpireResponse(expired_count=count)


def _build_preview_actions(
    appointments: list[Appointment],
    resource_id: str,
    preserve_locked_level: int,
    day_shift: int,
) -> tuple[list[str], list[dict[str, Any]], int]:
    original_ids: list[str] = []
    suggested_actions: list[dict[str, Any]] = []
    skipped_locked = 0

    for appt in appointments:
        lock_level = int(appt.lock_level or 0)
        if lock_level >= preserve_locked_level:
            skipped_locked += 1
            continue

        if not appt.starts_at or not appt.ends_at:
            continue
        if not appt.project_id and not appt.call_request_id:
            continue

        new_start = appt.starts_at + timedelta(days=day_shift)
        new_end = appt.ends_at + timedelta(days=day_shift)
        original_ids.append(str(appt.id))
        suggested_actions.append({"action": "CANCEL", "appointment_id": str(appt.id)})
        suggested_actions.append(
            {
                "action": "CREATE",
                "project_id": str(appt.project_id) if appt.project_id else None,
                "call_request_id": str(appt.call_request_id) if appt.call_request_id else None,
                "visit_type": appt.visit_type or "PRIMARY",
                "resource_id": resource_id,
                "starts_at": new_start.isoformat(),
                "ends_at": new_end.isoformat(),
                "weather_class": appt.weather_class or "MIXED",
            }
        )

    return original_ids, suggested_actions, skipped_locked


def _scope_window(route_date: date, scope: RescheduleScope) -> tuple[date, date, int]:
    if scope == RescheduleScope.WEEK:
        return route_date, route_date + timedelta(days=6), 7
    return route_date, route_date, 1


@router.post("/admin/schedule/daily-approve", response_model=DailyApproveResponse)
async def daily_batch_approve(
    payload: DailyApproveRequest,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.enable_schedule_engine:
        raise HTTPException(404, "Nerastas")

    now = _now_utc()
    resource_uuid = None
    resource_id_value = payload.resource_id.strip() if payload.resource_id else ""
    if resource_id_value:
        resource_uuid = _parse_uuid(resource_id_value, "resource_id")
    else:
        # In single-operator mode, allow approving all resources for the day.
        resource_id_value = "ALL"

    filters = [
        Appointment.status == "CONFIRMED",
        (
            (Appointment.route_date == payload.route_date)
            | (Appointment.route_date.is_(None) & (func.date(Appointment.starts_at) == payload.route_date))
        ),
    ]
    if resource_uuid is not None:
        filters.append(Appointment.resource_id == resource_uuid)

    stmt = _with_for_update_if_supported(
        select(Appointment).where(*filters).order_by(asc(Appointment.starts_at), asc(Appointment.id)),
        db,
    )
    rows = db.execute(stmt).scalars().all()
    if not rows:
        raise HTTPException(404, "Nėra patvirtintų susitikimų pasirinktai maršruto dienai")

    updated = 0
    changed_ids: list[str] = []
    for appt in rows:
        old_level = int(appt.lock_level or 0)
        if old_level >= 2:
            continue
        appt.lock_level = 2
        appt.locked_at = now
        appt.locked_by = _user_fk_or_none(db, current_user.id)
        appt.lock_reason = "DAILY_BATCH_APPROVE"
        appt.row_version = int(appt.row_version or 1) + 1
        updated += 1
        changed_ids.append(str(appt.id))

        create_audit_log(
            db,
            entity_type="appointment",
            entity_id=str(appt.id),
            action="APPOINTMENT_LOCK_LEVEL_CHANGED",
            old_value={"lock_level": old_level},
            new_value={"lock_level": 2},
            actor_type=current_user.role,
            actor_id=current_user.id,
            ip_address=None,
            user_agent=None,
            metadata={
                "reason": "DAILY_BATCH_APPROVE",
                "comment": payload.comment,
                "route_date": payload.route_date.isoformat(),
                "resource_id": resource_id_value,
            },
        )

    schedule_day_id = _schedule_day_entity_id(
        route_date=payload.route_date.isoformat(),
        resource_id=resource_id_value,
    )
    create_audit_log(
        db,
        entity_type="schedule_day",
        entity_id=schedule_day_id,
        action="DAILY_BATCH_APPROVED",
        old_value=None,
        new_value={"updated_count": updated, "appointment_ids": changed_ids},
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=None,
        user_agent=None,
        metadata={
            "reason": "DAILY_BATCH_APPROVE",
            "comment": payload.comment,
            "route_date": payload.route_date.isoformat(),
            "resource_id": resource_id_value,
        },
    )

    db.commit()
    return DailyApproveResponse(success=True, updated_count=updated)


@router.post("/admin/schedule/reschedule/preview", response_model=ReschedulePreviewResponse)
async def reschedule_preview(
    payload: ReschedulePreviewRequest,
    current_user: CurrentUser = Depends(require_roles("SUBCONTRACTOR", "ADMIN")),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.enable_schedule_engine:
        raise HTTPException(404, "Nerastas")

    resource_id_value = (payload.resource_id or "").strip() or (settings.schedule_default_resource_id or "").strip()
    if not resource_id_value:
        # Last resort: allow the operator to reschedule their own calendar if user exists in DB.
        resource_id_value = str(current_user.id or "").strip()
    if not resource_id_value:
        raise HTTPException(400, "Truksta resource_id")

    resource_uuid = _parse_uuid(resource_id_value, "resource_id")

    scope_start, scope_end, day_shift = _scope_window(payload.route_date, payload.scope)
    date_filter = (
        Appointment.route_date.is_not(None)
        & (Appointment.route_date >= scope_start)
        & (Appointment.route_date <= scope_end)
    ) | (
        Appointment.route_date.is_(None)
        & (func.date(Appointment.starts_at) >= scope_start)
        & (func.date(Appointment.starts_at) <= scope_end)
    )

    stmt = (
        select(Appointment)
        .where(
            Appointment.resource_id == resource_uuid,
            Appointment.status.in_(["CONFIRMED"]),
            date_filter,
        )
        .order_by(asc(Appointment.starts_at), asc(Appointment.id))
    )
    rows = db.execute(stmt).scalars().all()
    if not rows:
        raise HTTPException(404, "Nėra susitikimų pasirinktai dienai/resursui")

    original_ids, actions, skipped_locked = _build_preview_actions(
        rows,
        resource_id=resource_id_value,
        preserve_locked_level=payload.rules.preserve_locked_level,
        day_shift=day_shift,
    )
    if not actions:
        raise HTTPException(400, "Nėra perkeliamų susitikimų peržiūrai")

    preview_payload = _preview_payload(
        route_date=payload.route_date.isoformat(),
        resource_id=resource_id_value,
        original_appointment_ids=original_ids,
        suggested_actions=actions,
    )
    preview_hash = _preview_hash(preview_payload)
    now = _now_utc()
    expires_at = now + timedelta(minutes=max(1, settings.schedule_preview_ttl_minutes))

    preview = SchedulePreview(
        route_date=payload.route_date,
        resource_id=resource_uuid,
        preview_hash=preview_hash,
        payload=preview_payload,
        expires_at=expires_at,
        created_by=_user_fk_or_none(db, current_user.id),
    )
    db.add(preview)
    db.commit()
    db.refresh(preview)

    ids_set = set(original_ids)
    expected_versions = {str(row.id): int(row.row_version or 1) for row in rows if str(row.id) in ids_set}

    return ReschedulePreviewResponse(
        preview_id=str(preview.id),
        preview_hash=preview_hash,
        preview_expires_at=expires_at,
        original_appointment_ids=original_ids,
        expected_versions=expected_versions,
        suggested_actions=[SuggestedAction.model_validate(item) for item in actions],
        summary=RescheduleSummary(
            cancel_count=len([a for a in actions if a["action"] == "CANCEL"]),
            create_count=len([a for a in actions if a["action"] == "CREATE"]),
            total_travel_minutes=0,
            skipped_locked_count=skipped_locked,
        ),
    )


def _resolve_confirm_payload(
    payload: RescheduleConfirmRequest,
    db: Session,
) -> tuple[dict[str, Any], str]:
    settings = get_settings()
    now = _now_utc()

    if settings.schedule_use_server_preview:
        preview_uuid = _parse_uuid(payload.preview_id, "preview_id")
        preview = db.get(SchedulePreview, preview_uuid)
        if not preview:
            raise HTTPException(404, "Peržiūra nerasta")
        if preview.consumed_at is not None:
            raise HTTPException(409, "Peržiūra jau panaudota")
        if preview.expires_at <= now:
            raise HTTPException(409, "Peržiūra pasibaigė")
        if preview.preview_hash != payload.preview_hash:
            raise HTTPException(409, "Peržiūros hash nesutampa")
        return preview.payload, str(preview.id)

    if not payload.route_date or not payload.resource_id:
        raise HTTPException(400, "Stateless rezime privalomi route_date ir resource_id")
    if not payload.original_appointment_ids or not payload.suggested_actions:
        raise HTTPException(
            400,
            "Stateless rezime privalomi original_appointment_ids ir suggested_actions",
        )

    raw_actions = [a.model_dump(mode="json") for a in payload.suggested_actions]
    preview_payload = _preview_payload(
        route_date=payload.route_date.isoformat(),
        resource_id=payload.resource_id,
        original_appointment_ids=payload.original_appointment_ids,
        suggested_actions=raw_actions,
    )
    if _preview_hash(preview_payload) != payload.preview_hash:
        raise HTTPException(409, "Peržiūros hash nesutampa")
    return preview_payload, payload.preview_id


@router.post("/admin/schedule/reschedule/confirm", response_model=RescheduleConfirmResponse)
async def reschedule_confirm(
    payload: RescheduleConfirmRequest,
    current_user: CurrentUser = Depends(require_roles("SUBCONTRACTOR", "ADMIN")),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.enable_schedule_engine:
        raise HTTPException(404, "Nerastas")

    preview_data, preview_id = _resolve_confirm_payload(payload, db)
    route_date = str(preview_data.get("route_date", ""))
    resource_id = str(preview_data.get("resource_id", ""))
    original_ids = [str(i) for i in preview_data.get("original_appointment_ids", [])]
    suggested_actions = preview_data.get("suggested_actions", [])
    if not original_ids:
        raise HTTPException(400, "Tuščias original_appointment_ids sąrašas")

    original_uuid_ids = [_parse_uuid(item, "original_appointment_ids") for item in original_ids]
    stmt = _with_for_update_if_supported(select(Appointment).where(Appointment.id.in_(original_uuid_ids)), db)
    original_rows = db.execute(stmt).scalars().all()
    rows_by_id = {str(row.id): row for row in original_rows}
    if len(rows_by_id) != len(original_ids):
        raise HTTPException(409, "Pradiniai susitikimai pasikeitė")

    expected_versions = payload.expected_versions or {}
    for appointment_id in original_ids:
        row = rows_by_id.get(appointment_id)
        if row is None:
            raise HTTPException(409, "Pradiniai susitikimai pasikeitė")
        expected = expected_versions.get(appointment_id)
        if expected is None:
            raise HTTPException(400, f"Truksta expected version: {appointment_id}")
        current_version = int(row.row_version or 1)
        if current_version != int(expected):
            raise HTTPException(409, f"Versijos konfliktas: {appointment_id}")

        lock_level = int(row.lock_level or 0)
        if lock_level >= 2 and current_user.role != "ADMIN":
            raise HTTPException(403, "Tik ADMIN gali perplanuoti lock_level>=2 susitikimus")

    create_actions = [a for a in suggested_actions if a.get("action") == "CREATE"]
    if not create_actions:
        raise HTTPException(400, "Nėra CREATE veiksmų peržiūroje")

    now = _now_utc()
    reason = payload.reason.value
    metadata_common = {
        "reason": reason,
        "comment": payload.comment,
        "reschedule_preview_id": preview_id,
    }

    for appointment_id in original_ids:
        row = rows_by_id[appointment_id]
        old_status = row.status
        row.status = "CANCELLED"
        row.cancelled_at = now
        row.cancelled_by = _user_fk_or_none(db, current_user.id)
        row.cancel_reason = f"RESCHEDULE:{reason}"
        row.hold_expires_at = None
        row.row_version = int(row.row_version or 1) + 1
        create_audit_log(
            db,
            entity_type="appointment",
            entity_id=str(row.id),
            action="APPOINTMENT_CANCELLED",
            old_value={"status": old_status},
            new_value={"status": "CANCELLED"},
            actor_type=current_user.role,
            actor_id=current_user.id,
            ip_address=None,
            user_agent=None,
            metadata=metadata_common,
        )

    new_rows: list[Appointment] = []
    for action in create_actions:
        starts_at = datetime.fromisoformat(str(action.get("starts_at")))
        ends_at = datetime.fromisoformat(str(action.get("ends_at")))
        if ends_at <= starts_at:
            raise HTTPException(400, "Neteisingas CREATE veiksmo laiko langas")

        row = Appointment(
            project_id=action.get("project_id"),
            call_request_id=action.get("call_request_id"),
            resource_id=_parse_uuid(action.get("resource_id"), "resource_id"),
            visit_type=(action.get("visit_type") or "PRIMARY"),
            starts_at=starts_at,
            ends_at=ends_at,
            status="CONFIRMED",
            lock_level=1,
            weather_class=action.get("weather_class") or "MIXED",
            route_date=starts_at.date(),
            row_version=1,
            notes="RESCHEDULED",
        )
        db.add(row)
        db.flush()
        new_rows.append(row)

        create_audit_log(
            db,
            entity_type="appointment",
            entity_id=str(row.id),
            action="APPOINTMENT_CONFIRMED",
            old_value=None,
            new_value={
                "status": row.status,
                "starts_at": row.starts_at.isoformat(),
                "ends_at": row.ends_at.isoformat(),
                "visit_type": row.visit_type,
            },
            actor_type=current_user.role,
            actor_id=current_user.id,
            ip_address=None,
            user_agent=None,
            metadata=metadata_common,
        )

    for idx, old_id in enumerate(original_ids):
        if idx >= len(new_rows):
            break
        rows_by_id[old_id].superseded_by_id = new_rows[idx].id

    impacted_projects = {
        str(row.project_id) for row in list(rows_by_id.values()) + new_rows if row.project_id is not None
    }
    for project_id in impacted_projects:
        _sync_project_scheduled_for(db, project_id)

    schedule_day_id = _schedule_day_entity_id(route_date=route_date, resource_id=resource_id)
    create_audit_log(
        db,
        entity_type="schedule_day",
        entity_id=schedule_day_id,
        action="SCHEDULE_RESCHEDULED",
        old_value={"original_appointment_ids": original_ids},
        new_value={"new_appointment_ids": [str(row.id) for row in new_rows]},
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=None,
        user_agent=None,
        metadata={
            **metadata_common,
            "route_date": route_date,
            "resource_id": resource_id,
        },
    )

    if settings.schedule_use_server_preview:
        preview = db.get(SchedulePreview, _parse_uuid(payload.preview_id, "preview_id"))
        if preview:
            preview.consumed_at = now

    notifications_enqueued = False
    if settings.enable_notification_outbox:
        for appt in new_rows:
            # Extract contact info from CallRequest or Project
            email: str | None = None
            phone: str | None = None
            if appt.call_request_id is not None:
                lead = db.get(CallRequest, appt.call_request_id)
                if lead:
                    email = str(lead.email).strip() if lead.email else None
                    phone = str(lead.phone).strip() if lead.phone else None
            elif appt.project_id is not None:
                project = db.get(Project, appt.project_id)
                if project:
                    email = _extract_email_from_client_info(project.client_info)
                    phone = _extract_phone_from_client_info(project.client_info)

            body = f"Jusu vizito laikas pakeistas. Naujas laikas: {_format_dt_local(appt.starts_at)}."

            # Primary channel: Email
            if email:
                created = enqueue_notification(
                    db,
                    entity_type="appointment",
                    entity_id=str(appt.id),
                    channel="email",
                    template_key="APPOINTMENT_RESCHEDULED",
                    payload_json={
                        "to": email,
                        "subject": "VejaPRO: vizito laikas pakeistas",
                        "body_text": body,
                    },
                )
                notifications_enqueued = notifications_enqueued or created

            # Secondary channel: WhatsApp (if phone available)
            if phone and settings.enable_whatsapp_ping:
                created = enqueue_notification(
                    db,
                    entity_type="appointment",
                    entity_id=str(appt.id),
                    channel="whatsapp_ping",
                    template_key="APPOINTMENT_RESCHEDULED",
                    payload_json={
                        "to": phone,
                        "message": body,
                    },
                )
                notifications_enqueued = notifications_enqueued or created

    db.commit()

    return RescheduleConfirmResponse(
        success=True,
        new_appointment_ids=[str(row.id) for row in new_rows],
        notifications_enqueued=notifications_enqueued,
    )
