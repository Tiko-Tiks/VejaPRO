from __future__ import annotations

import re
import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import get_db
from app.models.project import Appointment, CallRequest, ConversationLock, User
from app.schemas.assistant import CallRequestStatus
from app.schemas.schedule import ConversationChannel
from app.services.transition_service import create_audit_log
from app.utils.rate_limit import get_client_ip, get_user_agent, rate_limiter

router = APIRouter()
SYSTEM_ENTITY_ID = "00000000-0000-0000-0000-000000000000"
VILNIUS_TZ = ZoneInfo("Europe/Vilnius")


def _now_utc() -> datetime:
    # SQLite (used in CI/tests) stores timezone-aware datetimes as naive values.
    # Use a naive UTC "now" for SQLite to avoid naive/aware comparison crashes.
    settings = get_settings()
    if (settings.database_url or "").startswith("sqlite"):
        # datetime.utcnow() is deprecated; keep the same naive-UTC semantics.
        return datetime.now(timezone.utc).replace(tzinfo=None)
    return datetime.now(timezone.utc)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _is_confirm_intent(text: str) -> bool:
    s = _norm(text)
    return s in {"tinka", "taip", "gerai", "ok", "sutinku"}


def _is_cancel_intent(text: str) -> bool:
    s = _norm(text)
    return s in {"netinka", "ne", "atsisakau"}


def _pick_default_resource_id(db: Session) -> uuid.UUID | None:
    settings = get_settings()
    if settings.schedule_default_resource_id:
        try:
            return uuid.UUID(settings.schedule_default_resource_id)
        except ValueError:
            return None

    row = (
        db.execute(select(User.id).where(User.is_active.is_(True)).order_by(User.created_at.asc()).limit(1))
        .scalars()
        .first()
    )
    return row


def _find_next_free_slot(
    db: Session,
    *,
    resource_id: uuid.UUID,
    duration_min: int,
    horizon_days: int = 14,
) -> tuple[datetime, datetime] | None:
    now_local = datetime.now(VILNIUS_TZ)
    duration = timedelta(minutes=max(15, duration_min))

    candidate_hours = [10, 13, 16]
    open_from = time(9, 0)
    open_to = time(18, 0)

    for day_offset in range(0, horizon_days):
        d = now_local.date() + timedelta(days=day_offset)
        if d.weekday() == 6:
            continue

        for hour in candidate_hours:
            start_local = datetime.combine(d, time(hour, 0), tzinfo=VILNIUS_TZ)
            end_local = start_local + duration
            if start_local.time() < open_from or end_local.time() > open_to:
                continue
            if start_local < now_local + timedelta(minutes=15):
                continue

            start_utc = start_local.astimezone(timezone.utc)
            end_utc = end_local.astimezone(timezone.utc)

            conflict = (
                db.execute(
                    select(Appointment.id).where(
                        Appointment.resource_id == resource_id,
                        Appointment.status.in_(["HELD", "CONFIRMED"]),
                        Appointment.starts_at < end_utc,
                        Appointment.ends_at > start_utc,
                    )
                )
                .scalars()
                .first()
            )
            if conflict:
                continue

            return start_utc, end_utc

    return None


def _get_or_create_chat_call_request(
    db: Session,
    *,
    conversation_id: str,
    name: str,
    from_phone: str,
) -> CallRequest:
    existing = (
        db.execute(
            select(CallRequest).where(
                CallRequest.source == "chat",
                CallRequest.notes == conversation_id,
            )
        )
        .scalars()
        .one_or_none()
    )
    if existing:
        return existing

    call_request = CallRequest(
        name=name or "Chat",
        phone=from_phone or "unknown",
        email=None,
        preferred_time=None,
        notes=conversation_id,
        status=CallRequestStatus.NEW.value,
        source="chat",
    )
    db.add(call_request)
    db.flush()
    return call_request


@router.post("/webhook/chat/events")
async def chat_events(request: Request, db: Session = Depends(get_db)):
    """
    Minimal web chat event handler for V1.

    Contract:
    - Input JSON:
      {
        "conversation_id": "string",
        "message": "string",
        "from_phone": "optional",
        "name": "optional"
      }
    - Output JSON:
      {
        "reply": "string",
        "state": { ... small hints for UI ... }
      }

    Notes:
    - Deterministic, simple intent recognition: "tinka" / "netinka".
    - Uses the same `appointments` + `conversation_locks` hold mechanics as Voice.
    """
    settings = get_settings()
    if not settings.enable_call_assistant:
        raise HTTPException(404, "Nerastas")

    payload = await request.json()
    conversation_id = (payload.get("conversation_id") or "").strip()
    message = (payload.get("message") or "").strip()
    from_phone = (payload.get("from_phone") or "").strip()
    name = (payload.get("name") or "").strip()

    if not conversation_id or not message:
        raise HTTPException(400, "Truksta conversation_id arba message")

    ip = get_client_ip(request) or "unknown"
    if settings.rate_limit_api_enabled:
        # Conservative limits for public chat.
        allowed_ip, _ = rate_limiter.allow(f"chat:ip:{ip}", 30, 60)
        allowed_conv, _ = rate_limiter.allow(f"chat:conv:{conversation_id}", 20, 60)
        if not (allowed_ip and allowed_conv):
            raise HTTPException(429, "Per daug uzklausu")

    now = _now_utc()
    lock = (
        db.execute(
            select(ConversationLock).where(
                ConversationLock.channel == ConversationChannel.CHAT.value,
                ConversationLock.conversation_id == conversation_id,
                ConversationLock.hold_expires_at > now,
            )
        )
        .scalars()
        .one_or_none()
    )

    # Always record a call request for chat (idempotent by conversation_id), even if we cannot schedule a hold.
    # Keep commit deferred so it can be atomic with subsequent HOLD creation.
    call_request = _get_or_create_chat_call_request(
        db,
        conversation_id=conversation_id,
        name=name,
        from_phone=from_phone,
    )

    # Confirm/cancel existing hold.
    if lock and _is_confirm_intent(message):
        appt = (
            db.execute(select(Appointment).where(Appointment.id == lock.appointment_id).with_for_update())
            .scalars()
            .one_or_none()
        )
        if not appt or appt.status != "HELD" or (appt.hold_expires_at and appt.hold_expires_at <= now):
            return {
                "reply": "Rezervacija nebegalioja. Parasykite, ir pasiulysiu kita laika.",
                "state": {"status": "expired"},
            }

        appt.status = "CONFIRMED"
        appt.hold_expires_at = None
        appt.lock_level = 1
        appt.locked_at = now
        appt.lock_reason = "HOLD_CONFIRM"
        appt.row_version = int(appt.row_version or 1) + 1

        db.delete(lock)

        if appt.call_request_id:
            call_req = db.get(CallRequest, appt.call_request_id)
            if call_req and call_req.status != CallRequestStatus.SCHEDULED.value:
                call_req.status = CallRequestStatus.SCHEDULED.value

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
            },
            actor_type="SUBCONTRACTOR",
            actor_id=None,
            ip_address=ip,
            user_agent=get_user_agent(request),
            metadata={"system_source": "chat_assistant", "conversation_id": conversation_id},
        )

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return {
                "reply": "Nepavyko patvirtinti laiko del konflikto. Parasykite, ir pasiulysiu kita varianta.",
                "state": {"status": "conflict"},
            }

        return {"reply": "Aciu. Laikas patvirtintas.", "state": {"status": "confirmed"}}

    if lock and _is_cancel_intent(message):
        appt = (
            db.execute(select(Appointment).where(Appointment.id == lock.appointment_id).with_for_update())
            .scalars()
            .one_or_none()
        )
        if appt and appt.status == "HELD":
            appt.status = "CANCELLED"
            appt.cancelled_at = now
            appt.cancel_reason = "HOLD_CANCELLED"
            appt.hold_expires_at = None
            appt.row_version = int(appt.row_version or 1) + 1

            create_audit_log(
                db,
                entity_type="appointment",
                entity_id=str(appt.id),
                action="APPOINTMENT_CANCELLED",
                old_value={"status": "HELD"},
                new_value={"status": "CANCELLED"},
                actor_type="SUBCONTRACTOR",
                actor_id=None,
                ip_address=ip,
                user_agent=get_user_agent(request),
                metadata={"system_source": "chat_assistant", "conversation_id": conversation_id},
            )

        db.delete(lock)
        db.commit()
        return {
            "reply": "Gerai. Laikas atsauktas. Parasykite, ir pasiulysiu kita laika.",
            "state": {"status": "cancelled"},
        }

    # If schedule engine disabled: record lead only.
    if not settings.enable_schedule_engine:
        db.commit()

        return {
            "reply": "Aciu. Uzklausa uzregistruota. Susisieksime artimiausiu metu.",
            "state": {"status": "recorded"},
        }

    # Propose a slot and create HOLD.
    # NOTE: do NOT commit here — keep it atomic with HOLD creation.

    resource_id = _pick_default_resource_id(db)
    if not resource_id:
        db.commit()  # persist the lead before returning
        return {
            "reply": "Sistema nesukonfiguruota planavimui. Uzklausa uzregistruota. Susisieksime.",
            "state": {"status": "not_configured"},
        }

    slot = _find_next_free_slot(db, resource_id=resource_id, duration_min=60)
    if not slot:
        db.commit()  # persist the lead before returning
        return {
            "reply": "Laisvu laiku neradau. Uzklausa uzregistruota. Susisieksime del laiko.",
            "state": {"status": "no_slots"},
        }

    start_utc, end_utc = slot
    start_local = start_utc.astimezone(VILNIUS_TZ)

    call_request.preferred_time = start_utc

    hold_expires_at = now + timedelta(minutes=max(1, settings.schedule_hold_duration_minutes))
    appt = Appointment(
        project_id=None,
        call_request_id=call_request.id,
        resource_id=resource_id,
        visit_type="PRIMARY",
        starts_at=start_utc,
        ends_at=end_utc,
        status="HELD",
        lock_level=0,
        hold_expires_at=hold_expires_at,
        weather_class="MIXED",
        route_date=start_local.date(),
        row_version=1,
        notes="HOLD",
    )
    db.add(appt)
    db.flush()

    conv_lock = ConversationLock(
        channel=ConversationChannel.CHAT.value,
        conversation_id=conversation_id,
        appointment_id=appt.id,
        visit_type=appt.visit_type,
        hold_expires_at=hold_expires_at,
    )
    db.add(conv_lock)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # The whole transaction (including call_request) was rolled back.
        # Re-persist the call_request so the lead is not lost.
        _get_or_create_chat_call_request(
            db,
            conversation_id=conversation_id,
            name=name,
            from_phone=from_phone,
        )
        db.commit()
        return {
            "reply": "Laikas ka tik tapo neprieinamas. Uzklausa uzregistruota. Susisieksime.",
            "state": {"status": "conflict"},
        }

    reply = (
        f"Galiu rezervuoti laika {start_local.strftime('%Y-%m-%d')} {start_local.strftime('%H:%M')}. "
        "Jei tinka, parasykite 'Tinka'. Jei netinka, parasykite 'Netinka'."
    )
    return {
        "reply": reply,
        "state": {
            "status": "held",
            "hold_expires_at": hold_expires_at.isoformat(),
            "starts_at": start_utc.isoformat(),
            "ends_at": end_utc.isoformat(),
        },
    }
