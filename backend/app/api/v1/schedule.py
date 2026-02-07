from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import asc, func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.models.project import Appointment, Project, SchedulePreview
from app.schemas.schedule import (
    RescheduleConfirmRequest,
    RescheduleConfirmResponse,
    ReschedulePreviewRequest,
    ReschedulePreviewResponse,
    RescheduleSummary,
    SuggestedAction,
)
from app.services.transition_service import create_audit_log


router = APIRouter()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(400, f"Invalid {field_name}") from exc


def _canonical_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _preview_payload(
    route_date: str,
    resource_id: str,
    original_appointment_ids: List[str],
    suggested_actions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "route_date": route_date,
        "resource_id": resource_id,
        "original_appointment_ids": original_appointment_ids,
        "suggested_actions": suggested_actions,
    }


def _preview_hash(payload: Dict[str, Any]) -> str:
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

    earliest = (
        db.execute(
            select(func.min(Appointment.starts_at)).where(
                Appointment.project_id == project.id,
                Appointment.status == "CONFIRMED",
                Appointment.visit_type == "PRIMARY",
            )
        )
        .scalar_one_or_none()
    )
    project.scheduled_for = earliest


def _build_preview_actions(
    appointments: List[Appointment],
    resource_id: str,
    preserve_locked_level: int,
) -> Tuple[List[str], List[Dict[str, Any]], int]:
    original_ids: List[str] = []
    suggested_actions: List[Dict[str, Any]] = []
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

        new_start = appt.starts_at + timedelta(days=1)
        new_end = appt.ends_at + timedelta(days=1)
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


@router.post("/admin/schedule/reschedule/preview", response_model=ReschedulePreviewResponse)
async def reschedule_preview(
    payload: ReschedulePreviewRequest,
    current_user: CurrentUser = Depends(require_roles("SUBCONTRACTOR", "ADMIN")),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.enable_schedule_engine:
        raise HTTPException(404, "Not found")

    resource_uuid = _parse_uuid(payload.resource_id, "resource_id")

    stmt = (
        select(Appointment)
        .where(
            Appointment.resource_id == resource_uuid,
            Appointment.status.in_(["CONFIRMED", "SCHEDULED"]),
            (
                (Appointment.route_date == payload.route_date)
                | (
                    Appointment.route_date.is_(None)
                    & (func.date(Appointment.starts_at) == payload.route_date)
                )
            ),
        )
        .order_by(asc(Appointment.starts_at), asc(Appointment.id))
    )
    rows = db.execute(stmt).scalars().all()
    if not rows:
        raise HTTPException(404, "No appointments for selected route day/resource")

    original_ids, actions, skipped_locked = _build_preview_actions(
        rows,
        resource_id=payload.resource_id,
        preserve_locked_level=payload.rules.preserve_locked_level,
    )
    if not actions:
        raise HTTPException(400, "No movable appointments for preview")

    preview_payload = _preview_payload(
        route_date=payload.route_date.isoformat(),
        resource_id=payload.resource_id,
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
        created_by=_parse_uuid(current_user.id, "current_user.id"),
    )
    db.add(preview)
    db.commit()
    db.refresh(preview)

    return ReschedulePreviewResponse(
        preview_id=str(preview.id),
        preview_hash=preview_hash,
        preview_expires_at=expires_at,
        original_appointment_ids=original_ids,
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
) -> Tuple[Dict[str, Any], str]:
    settings = get_settings()
    now = _now_utc()

    if settings.schedule_use_server_preview:
        preview_uuid = _parse_uuid(payload.preview_id, "preview_id")
        preview = db.get(SchedulePreview, preview_uuid)
        if not preview:
            raise HTTPException(404, "Preview not found")
        if preview.consumed_at is not None:
            raise HTTPException(409, "Preview already consumed")
        if preview.expires_at <= now:
            raise HTTPException(409, "Preview expired")
        if preview.preview_hash != payload.preview_hash:
            raise HTTPException(409, "Preview hash mismatch")
        return preview.payload, str(preview.id)

    if not payload.route_date or not payload.resource_id:
        raise HTTPException(400, "route_date and resource_id are required in stateless mode")
    if not payload.original_appointment_ids or not payload.suggested_actions:
        raise HTTPException(400, "original_appointment_ids and suggested_actions required in stateless mode")

    raw_actions = [a.model_dump(mode="json") for a in payload.suggested_actions]
    preview_payload = _preview_payload(
        route_date=payload.route_date.isoformat(),
        resource_id=payload.resource_id,
        original_appointment_ids=payload.original_appointment_ids,
        suggested_actions=raw_actions,
    )
    if _preview_hash(preview_payload) != payload.preview_hash:
        raise HTTPException(409, "Preview hash mismatch")
    return preview_payload, payload.preview_id


@router.post("/admin/schedule/reschedule/confirm", response_model=RescheduleConfirmResponse)
async def reschedule_confirm(
    payload: RescheduleConfirmRequest,
    current_user: CurrentUser = Depends(require_roles("SUBCONTRACTOR", "ADMIN")),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.enable_schedule_engine:
        raise HTTPException(404, "Not found")

    preview_data, preview_id = _resolve_confirm_payload(payload, db)
    route_date = str(preview_data.get("route_date", ""))
    resource_id = str(preview_data.get("resource_id", ""))
    original_ids = [str(i) for i in preview_data.get("original_appointment_ids", [])]
    suggested_actions = preview_data.get("suggested_actions", [])
    if not original_ids:
        raise HTTPException(400, "Empty original_appointment_ids")

    original_uuid_ids = [_parse_uuid(item, "original_appointment_ids") for item in original_ids]
    original_rows = (
        db.execute(
            select(Appointment)
            .where(Appointment.id.in_(original_uuid_ids))
            .with_for_update()
        )
        .scalars()
        .all()
    )
    rows_by_id = {str(row.id): row for row in original_rows}
    if len(rows_by_id) != len(original_ids):
        raise HTTPException(409, "Original appointments changed")

    expected_versions = payload.expected_versions or {}
    for appointment_id in original_ids:
        row = rows_by_id.get(appointment_id)
        if row is None:
            raise HTTPException(409, "Original appointments changed")
        expected = expected_versions.get(appointment_id)
        if expected is None:
            raise HTTPException(400, f"Missing expected version for {appointment_id}")
        current_version = int(row.row_version or 1)
        if current_version != int(expected):
            raise HTTPException(409, f"Row version conflict for {appointment_id}")

        lock_level = int(row.lock_level or 0)
        if lock_level >= 2 and current_user.role != "ADMIN":
            raise HTTPException(403, "Only ADMIN can reschedule lock_level>=2 appointments")

    create_actions = [a for a in suggested_actions if a.get("action") == "CREATE"]
    if not create_actions:
        raise HTTPException(400, "No CREATE actions in preview")

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
        row.cancelled_by = _parse_uuid(current_user.id, "current_user.id")
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

    new_rows: List[Appointment] = []
    for action in create_actions:
        starts_at = datetime.fromisoformat(str(action.get("starts_at")))
        ends_at = datetime.fromisoformat(str(action.get("ends_at")))
        if ends_at <= starts_at:
            raise HTTPException(400, "Invalid CREATE action time window")

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
        str(row.project_id)
        for row in list(rows_by_id.values()) + new_rows
        if row.project_id is not None
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

    db.commit()

    return RescheduleConfirmResponse(
        success=True,
        new_appointment_ids=[str(row.id) for row in new_rows],
        notifications_enqueued=True,
    )
