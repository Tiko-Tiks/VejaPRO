from __future__ import annotations

import re
import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import and_, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Gather, VoiceResponse

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


def _twilio_request_url(request: Request) -> str:
    url = request.url
    proto = request.headers.get("x-forwarded-proto")
    host = request.headers.get("x-forwarded-host")
    if proto:
        url = url.replace(scheme=proto)
    if host:
        url = url.replace(netloc=host)
    return str(url)


def _twiml(response: VoiceResponse) -> Response:
    return Response(content=str(response), media_type="application/xml")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _is_confirm_intent(*, digits: str | None, speech: str | None) -> bool:
    if (digits or "").strip() == "1":
        return True
    s = _norm(speech or "")
    return any(token in s for token in ("tinka", "taip", "gerai", "sutinku", "ok"))


def _is_cancel_intent(*, digits: str | None, speech: str | None) -> bool:
    if (digits or "").strip() == "2":
        return True
    s = _norm(speech or "")
    return any(token in s for token in ("netinka", "ne", "atsisakau"))


def _parse_uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(400, f"Neteisingas {field_name}") from exc


def _pick_default_resource_id(db: Session) -> uuid.UUID | None:
    settings = get_settings()
    if settings.schedule_default_resource_id:
        try:
            return uuid.UUID(settings.schedule_default_resource_id)
        except ValueError:
            return None

    # Auto-pick earliest active operator-like user.
    row = (
        db.execute(
            select(User.id)
            .where(
                and_(
                    User.is_active.is_(True),
                    User.role.in_(["ADMIN", "SUBCONTRACTOR"]),
                )
            )
            .order_by(User.created_at.asc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    return row


def _find_next_free_slot(
    db: Session,
    *,
    resource_id: uuid.UUID,
    duration_min: int,
    not_before_utc: datetime | None = None,
    horizon_days: int = 14,
) -> tuple[datetime, datetime] | None:
    """
    Minimal deterministic slot finder for V1 Voice MVP.
    - Uses fixed candidate times (10:00, 13:00, 16:00 Europe/Vilnius).
    - Avoids overlap with HELD/CONFIRMED for the resource.
    - Stores times in UTC.
    """
    now_local = datetime.now(VILNIUS_TZ)
    duration = timedelta(minutes=max(15, duration_min))

    not_before_aware: datetime | None = None
    if not_before_utc is not None:
        not_before_aware = not_before_utc
        if not_before_aware.tzinfo is None:
            not_before_aware = not_before_aware.replace(tzinfo=timezone.utc)
        else:
            not_before_aware = not_before_aware.astimezone(timezone.utc)

    candidate_hours = [10, 13, 16]
    open_from = time(9, 0)
    open_to = time(18, 0)

    for day_offset in range(0, horizon_days):
        d = now_local.date() + timedelta(days=day_offset)
        # Skip Sundays (0=Mon ... 6=Sun)
        if d.weekday() == 6:
            continue

        for hour in candidate_hours:
            start_local = datetime.combine(d, time(hour, 0), tzinfo=VILNIUS_TZ)
            end_local = start_local + duration

            if start_local.time() < open_from or end_local.time() > open_to:
                continue
            if start_local < now_local + timedelta(minutes=30):
                continue

            start_utc = start_local.astimezone(timezone.utc)
            end_utc = end_local.astimezone(timezone.utc)

            if not_before_aware is not None and start_utc <= not_before_aware:
                continue

            # Overlap check: any HELD/CONFIRMED that intersects.
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


def _as_utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _find_active_held_for_phone(db: Session, *, from_phone: str, now: datetime) -> Appointment | None:
    """Extra concurrency guard: one active HELD per client phone across calls (CallSid)."""
    if not from_phone:
        return None

    return (
        db.execute(
            select(Appointment)
            .join(CallRequest, Appointment.call_request_id == CallRequest.id)
            .where(
                CallRequest.phone == from_phone,
                Appointment.status == "HELD",
                Appointment.hold_expires_at.is_not(None),
                Appointment.hold_expires_at > now,
            )
            .order_by(Appointment.hold_expires_at.desc(), Appointment.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def _ensure_twilio_signature_or_empty(
    request: Request,
    form: dict,
    *,
    path_for_audit: str,
    from_phone: str | None,
    db: Session,
) -> bool:
    settings = get_settings()
    if settings.allow_insecure_webhooks:
        return True

    if not settings.twilio_auth_token:
        raise HTTPException(500, "Nesukonfigūruotas Twilio")

    signature = request.headers.get("X-Twilio-Signature")
    validator = RequestValidator(settings.twilio_auth_token)
    request_url = settings.twilio_voice_webhook_url or _twilio_request_url(request)
    if signature and validator.validate(request_url, dict(form), signature):
        return True

    create_audit_log(
        db,
        entity_type="system",
        entity_id=SYSTEM_ENTITY_ID,
        action="TWILIO_SIGNATURE_INVALID",
        old_value=None,
        new_value=None,
        actor_type="SYSTEM",
        actor_id=None,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        metadata={"path": path_for_audit, "from": from_phone},
    )
    db.commit()
    return False


def _get_or_create_voice_call_request(db: Session, *, call_sid: str, from_phone: str | None) -> CallRequest:
    existing = (
        db.execute(
            select(CallRequest).where(
                CallRequest.source == "voice",
                CallRequest.notes == str(call_sid),
            )
        )
        .scalars()
        .one_or_none()
    )
    if existing:
        return existing

    call_request = CallRequest(
        name="Skambutis",
        phone=from_phone or "unknown",
        email=None,
        preferred_time=None,
        notes=str(call_sid),
        status=CallRequestStatus.NEW.value,
        source="voice",
    )
    db.add(call_request)
    db.flush()
    return call_request


@router.post("/webhook/twilio/voice")
async def twilio_voice_webhook(request: Request, db: Session = Depends(get_db)):
    """
    V1 Voice MVP (deterministic):
    - Validates Twilio signature (or bypasses when ALLOW_INSECURE_WEBHOOKS=true).
    - Proposes a single slot and creates a HOLD before speaking it.
    - Confirms/cancels HOLD on simple intents ("tinka"/"netinka" or 1/2).
    """
    settings = get_settings()
    if not settings.enable_twilio:
        raise HTTPException(404, "Nerastas")
    if not settings.enable_call_assistant:
        raise HTTPException(404, "Nerastas")

    form_data = await request.form()
    form = dict(form_data)
    from_phone = form.get("From")
    call_sid = form.get("CallSid")
    digits = form.get("Digits")
    speech = form.get("SpeechResult")

    if not call_sid:
        raise HTTPException(400, "Truksta CallSid")

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
                ip_address=get_client_ip(request),
                user_agent=get_user_agent(request),
                metadata={
                    "path": "/api/v1/webhook/twilio/voice",
                    "key": key,
                    "limit": settings.rate_limit_twilio_from_per_min,
                    "window_seconds": 60,
                },
            )
            db.commit()
            vr = VoiceResponse()
            vr.say("Per daug uzklausu. Pabandykite veliau.")
            return _twiml(vr)

    if not _ensure_twilio_signature_or_empty(
        request,
        form,
        path_for_audit="/api/v1/webhook/twilio/voice",
        from_phone=from_phone,
        db=db,
    ):
        return Response(content="<Response></Response>", media_type="application/xml")

    # Always record call request (idempotent by CallSid), even if we cannot schedule a hold.
    # NOTE: do NOT db.commit() here — the helper already called db.flush()
    # to obtain call_request.id.  Deferring the commit keeps preferred_time
    # in the same transaction as the call_request creation, guaranteeing
    # atomicity (see bug: expired-object after mid-flow commit).
    call_request = _get_or_create_voice_call_request(db, call_sid=str(call_sid), from_phone=from_phone)

    # Detect existing hold for this call (active or expired).
    now = _now_utc()
    lock = (
        db.execute(
            select(ConversationLock).where(
                ConversationLock.channel == ConversationChannel.VOICE.value,
                ConversationLock.conversation_id == str(call_sid),
            )
        )
        .scalars()
        .one_or_none()
    )
    lock_active = bool(lock and lock.hold_expires_at and lock.hold_expires_at > now)
    if lock and not lock_active:
        # Expired lock: best-effort cleanup before creating a new hold. Keep it in the same transaction as new HOLD.
        db.delete(lock)
        lock = None

    # If we have a hold and user confirms/cancels, apply.
    if lock and lock_active and _is_confirm_intent(digits=digits, speech=speech):
        appt = (
            db.execute(select(Appointment).where(Appointment.id == lock.appointment_id).with_for_update())
            .scalars()
            .one_or_none()
        )
        vr = VoiceResponse()
        if not appt or appt.status != "HELD" or (appt.hold_expires_at and appt.hold_expires_at <= now):
            vr.say("Rezervacija nebegalioja. Pasiulysiu kita laika.")
            return _twiml(vr)

        appt.status = "CONFIRMED"
        appt.hold_expires_at = None
        appt.lock_level = 1
        appt.locked_at = now
        appt.lock_reason = "HOLD_CONFIRM"
        appt.row_version = int(appt.row_version or 1) + 1

        # Remove lock.
        db.delete(lock)

        # Mark call request as scheduled (if present).
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
                "visit_type": appt.visit_type,
            },
            actor_type="SYSTEM_TWILIO",
            actor_id=None,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            metadata={
                "reason": "HOLD_CONFIRM",
                "comment": "",
                "channel": ConversationChannel.VOICE.value,
                "conversation_id": str(call_sid),
            },
        )

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            vr.say("Nepavyko patvirtinti laiko del konflikto. Pasiulysiu kita varianta.")
            return _twiml(vr)

        vr.say("Aciu. Laikas patvirtintas. Iki pasimatymo.")
        return _twiml(vr)

    if lock and lock_active and _is_cancel_intent(digits=digits, speech=speech):
        appt = (
            db.execute(select(Appointment).where(Appointment.id == lock.appointment_id).with_for_update())
            .scalars()
            .one_or_none()
        )
        vr = VoiceResponse()
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
                actor_type="SYSTEM_TWILIO",
                actor_id=None,
                ip_address=get_client_ip(request),
                user_agent=get_user_agent(request),
                metadata={
                    "reason": "HOLD_CANCELLED",
                    "comment": "Voice cancel",
                    "channel": ConversationChannel.VOICE.value,
                    "conversation_id": str(call_sid),
                },
            )

        db.delete(lock)
        db.commit()
        vr.say("Gerai. Laikas atsauktas. Aciu uz skambuti.")
        return _twiml(vr)

    if lock and lock_active:
        # No confirm/cancel intent, but we do have an active hold: re-prompt the same held slot (idempotent behavior).
        appt = db.get(Appointment, lock.appointment_id)
        if appt and appt.status == "HELD" and (appt.hold_expires_at and appt.hold_expires_at > now):
            start_utc = _as_utc_aware(appt.starts_at)
            end_utc = _as_utc_aware(appt.ends_at)
            start_local = start_utc.astimezone(VILNIUS_TZ)

            gather = Gather(
                input="speech dtmf",
                num_digits=1,
                timeout=6,
                action="/api/v1/webhook/twilio/voice",
                method="POST",
            )
            gather.say(
                f"Galiu rezervuoti laika {start_local.strftime('%Y-%m-%d')} {start_local.strftime('%H:%M')}. "
                "Jei tinka, spauskite 1 arba sakykite tinka. Jei netinka, spauskite 2 arba sakykite netinka."
            )
            vr = VoiceResponse()
            vr.append(gather)
            vr.say("Negavau atsakymo. Pabandykime dar karta.")
            vr.redirect("/api/v1/webhook/twilio/voice", method="POST")
            return _twiml(vr)

        # Best-effort cleanup if DB state is inconsistent (lock exists, but appointment is missing/invalid).
        db.delete(lock)
        lock = None
        lock_active = False

    # If schedule engine is disabled, still record a call request and end politely.
    if not settings.enable_schedule_engine:
        db.commit()  # persist the lead before returning
        vr = VoiceResponse()
        vr.say("Aciu uz skambuti. Uzklausa uzregistruota. Mes susisieksime artimiausiu metu.")
        return _twiml(vr)

    # Phone-level concurrency: reuse an existing active HELD for this phone across different CallSid values.
    if from_phone:
        appt = _find_active_held_for_phone(db, from_phone=from_phone, now=now)
        if appt:
            hold_expires_at = now + timedelta(minutes=max(1, settings.schedule_hold_duration_minutes))

            # Take over the existing HELD for this call (delete previous conversation locks for that appt).
            db.execute(delete(ConversationLock).where(ConversationLock.appointment_id == appt.id))

            if appt.call_request_id != call_request.id:
                appt.call_request_id = call_request.id

            appt.hold_expires_at = hold_expires_at
            appt.row_version = (appt.row_version or 1) + 1
            call_request.preferred_time = _as_utc_aware(appt.starts_at)

            conv_lock = ConversationLock(
                channel=ConversationChannel.VOICE.value,
                conversation_id=str(call_sid),
                appointment_id=appt.id,
                visit_type=appt.visit_type,
                hold_expires_at=hold_expires_at,
            )
            db.add(conv_lock)
            db.commit()

            start_utc = _as_utc_aware(appt.starts_at)
            start_local = start_utc.astimezone(VILNIUS_TZ)

            gather = Gather(
                input="speech dtmf",
                num_digits=1,
                timeout=6,
                action="/api/v1/webhook/twilio/voice",
                method="POST",
            )
            gather.say(
                f"Galiu rezervuoti laika {start_local.strftime('%Y-%m-%d')} {start_local.strftime('%H:%M')}. "
                "Jei tinka, spauskite 1 arba sakykite tinka. Jei netinka, spauskite 2 arba sakykite netinka."
            )
            vr = VoiceResponse()
            vr.append(gather)
            vr.say("Negavau atsakymo. Pabandykime dar karta.")
            vr.redirect("/api/v1/webhook/twilio/voice", method="POST")
            return _twiml(vr)

    # No active hold: propose a slot and create a HOLD before speaking it.
    resource_id = _pick_default_resource_id(db)
    vr = VoiceResponse()
    if not resource_id:
        db.commit()  # persist the lead before returning
        vr.say("Sistema nesukonfiguruota planavimui. Uzklausa uzregistruota. Susisieksime.")
        return _twiml(vr)

    attempt_after: datetime | None = None
    for _ in range(0, 3):
        slot = _find_next_free_slot(
            db,
            resource_id=resource_id,
            duration_min=60,
            not_before_utc=attempt_after,
        )
        if not slot:
            db.commit()  # persist the lead before returning
            vr.say("Siandien laisvu laiku neradau. Uzklausa uzregistruota. Susisieksime del laiko.")
            return _twiml(vr)

        start_utc, end_utc = slot
        start_local = start_utc.astimezone(VILNIUS_TZ)

        call_request.preferred_time = start_utc

        appt = Appointment(
            project_id=None,
            call_request_id=call_request.id,
            resource_id=resource_id,
            visit_type="PRIMARY",
            starts_at=start_utc,
            ends_at=end_utc,
            status="HELD",
            lock_level=0,
            hold_expires_at=now + timedelta(minutes=max(1, settings.schedule_hold_duration_minutes)),
            weather_class="MIXED",
            route_date=start_local.date(),
            row_version=1,
            notes="HOLD",
        )
        db.add(appt)
        db.flush()

        conv_lock = ConversationLock(
            channel=ConversationChannel.VOICE.value,
            conversation_id=str(call_sid),
            appointment_id=appt.id,
            visit_type=appt.visit_type,
            hold_expires_at=appt.hold_expires_at,
        )
        db.add(conv_lock)

        try:
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            attempt_after = start_utc
            # The whole transaction (including call_request) was rolled back.
            # Re-persist the call_request so the lead is not lost.
            call_request = _get_or_create_voice_call_request(db, call_sid=str(call_sid), from_phone=from_phone)
    else:
        db.commit()
        vr.say("Laikas ka tik tapo neprieinamas. Uzklausa uzregistruota. Susisieksime.")
        return _twiml(vr)

    # Ask confirmation (DTMF 1/2 or speech).
    gather = Gather(
        input="speech dtmf",
        num_digits=1,
        timeout=6,
        action="/api/v1/webhook/twilio/voice",
        method="POST",
    )
    gather.say(
        f"Galiu rezervuoti laika {start_local.strftime('%Y-%m-%d')} {start_local.strftime('%H:%M')}. "
        "Jei tinka, spauskite 1 arba sakykite tinka. Jei netinka, spauskite 2 arba sakykite netinka."
    )
    vr.append(gather)
    vr.say("Negavau atsakymo. Pabandykime dar karta.")
    vr.redirect("/api/v1/webhook/twilio/voice", method="POST")
    return _twiml(vr)
