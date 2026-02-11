"""
V2.2 Unified Client Card — Intake Service

State machine for email-based lead intake:
  questionnaire → auto-prepare offer → one-click send → accept/reject

Adapters call existing Schedule Engine + Notification Outbox.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import get_settings
from app.models.project import Appointment, CallRequest, User
from app.services.notification_outbox import enqueue_notification
from app.services.transition_service import create_audit_log

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("email", "address", "service_type")
ALLOWED_QUESTIONNAIRE_FIELDS = (
    "email",
    "address",
    "service_type",
    "phone",
    "client_name",
    "area_m2",
    "whatsapp_consent",
    "notes",
    "urgency",
)
MAX_ATTEMPTS_DEFAULT = 5
DEFAULT_INSPECTION_DURATION_MIN = 60


class IntakeError(Exception):
    pass


class IntakeConflictError(IntakeError):
    pass


@dataclass(frozen=True)
class Actor:
    actor_type: str  # "ADMIN" | "SUBCONTRACTOR" | "CLIENT"
    actor_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]


@dataclass(frozen=True)
class SlotPreview:
    start: datetime
    end: datetime
    resource_id: str


# ─── Helpers ───────────────────────────────────────────


def _now_utc() -> datetime:
    settings = get_settings()
    if (settings.database_url or "").startswith("sqlite"):
        return datetime.now(timezone.utc).replace(tzinfo=None)
    return datetime.now(timezone.utc)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _mask_email(email: str) -> str:
    email = (email or "").strip()
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if not local:
        return f"*@{domain}"
    if len(local) == 1:
        return f"{local}*@{domain}"
    return f"{local[0]}***@{domain}"


# ─── intake_state accessors ───────────────────────────


def _get_intake_state(call_request: CallRequest) -> dict[str, Any]:
    state = call_request.intake_state
    if not isinstance(state, dict):
        return {}
    return state


def _set_intake_state(call_request: CallRequest, state: dict[str, Any]) -> None:
    call_request.intake_state = state
    flag_modified(call_request, "intake_state")


def _row_version(state: dict[str, Any]) -> int:
    return int(((state.get("workflow") or {}).get("row_version")) or 0)


def _bump_row_version(state: dict[str, Any]) -> None:
    state.setdefault("workflow", {})
    state["workflow"]["row_version"] = _row_version(state) + 1
    state["workflow"]["updated_at"] = _now_utc().isoformat()


def _set_phase(state: dict[str, Any], phase: str) -> None:
    state.setdefault("workflow", {})
    state["workflow"]["phase"] = phase
    state["workflow"]["updated_at"] = _now_utc().isoformat()


def _questionnaire_value(state: dict[str, Any], key: str) -> Optional[str]:
    """Extract questionnaire value, normalizing empty values to None."""
    q = state.get("questionnaire") or {}
    v = q.get(key)
    if isinstance(v, dict):
        # Return value or None if empty/missing
        val = v.get("value")
        return val if val else None
    if isinstance(v, str):
        return v if v else None
    return None


# ─── Questionnaire logic ──────────────────────────────


def questionnaire_complete(state: dict[str, Any]) -> bool:
    for key in REQUIRED_FIELDS:
        if not (_questionnaire_value(state, key) or "").strip():
            return False
    return True


def apply_intake_patch(
    state: dict[str, Any],
    patch: dict[str, Any],
    *,
    source: str,
    confidence: Optional[float] = None,
) -> dict[str, Any]:
    """Apply a patch to the questionnaire, validating field names.

    SECURITY: Only accepts known questionnaire fields to prevent injection.
    """
    state.setdefault("questionnaire", {})
    q = state["questionnaire"]

    for k, v in patch.items():
        # Validate that field is in allowlist
        if k not in ALLOWED_QUESTIONNAIRE_FIELDS:
            logger.warning("Ignoring unknown questionnaire field: %s (source: %s)", k, source)
            continue

        if k in ("whatsapp_consent", "notes"):
            q[k] = v
            continue
        if v is None:
            continue
        q[k] = {"value": v, "source": source, "confidence": confidence}

    _bump_row_version(state)
    return state


def merge_ai_suggestions(
    state: dict[str, Any],
    suggestions: dict[str, dict[str, Any]],
    *,
    min_confidence: float = 0.70,
) -> dict[str, Any]:
    state.setdefault("questionnaire", {})
    q = state["questionnaire"]

    for key, payload in suggestions.items():
        if key not in ALLOWED_QUESTIONNAIRE_FIELDS:
            continue
        if key in ("whatsapp_consent", "notes"):
            continue  # these don't have confidence structure

        conf = float(payload.get("confidence") or 0.0)
        val = payload.get("value")

        if not val or conf < min_confidence:
            continue

        existing = q.get(key)
        if isinstance(existing, dict) and existing.get("source") == "operator":
            continue  # operator-set fields are never overwritten by AI
        if isinstance(existing, dict) and existing.get("value"):
            existing_conf = float(existing.get("confidence") or 0.0)
            if conf <= existing_conf:
                continue  # lower or equal confidence doesn't overwrite

        q[key] = {"value": val, "source": "ai", "confidence": conf}

    _bump_row_version(state)
    return state


def compute_transcript_hash(transcript_text: str) -> str:
    return _sha256_hex(transcript_text.strip())


# ─── Offer container ──────────────────────────────────


def ensure_offer_container(state: dict[str, Any]) -> None:
    state.setdefault("active_offer", {})
    ao = state["active_offer"]
    ao.setdefault("state", "NONE")
    ao.setdefault("kind", "INSPECTION")
    ao.setdefault("slot", {"start": None, "end": None, "resource_id": None})
    ao.setdefault("appointment_id", None)
    ao.setdefault("hold_expires_at", None)
    ao.setdefault("token_hash", None)
    ao.setdefault("channel", "email")
    ao.setdefault("attempt_no", 0)
    state.setdefault("offer_history", [])


def set_prepared_offer(state: dict[str, Any], kind: str, slot: SlotPreview) -> None:
    ensure_offer_container(state)
    ao = state["active_offer"]
    ao["kind"] = kind
    ao["state"] = "PREPARED"
    ao["slot"] = {
        "start": slot.start.isoformat(),
        "end": slot.end.isoformat(),
        "resource_id": slot.resource_id,
    }
    ao["appointment_id"] = None
    ao["hold_expires_at"] = None
    ao["token_hash"] = None
    ao["channel"] = "email"
    _set_phase(state, "OFFER_PREPARED")
    _bump_row_version(state)


def set_sent_offer(
    state: dict[str, Any],
    *,
    appointment_id: str,
    hold_expires_at: datetime,
    public_token: str,
) -> None:
    ensure_offer_container(state)
    ao = state["active_offer"]
    ao["state"] = "SENT"
    ao["appointment_id"] = appointment_id
    ao["hold_expires_at"] = hold_expires_at.isoformat()
    ao["token_hash"] = _sha256_hex(public_token)
    ao["attempt_no"] = int(ao.get("attempt_no") or 0) + 1
    _set_phase(state, "OFFER_SENT")
    _bump_row_version(state)


def append_offer_history(
    state: dict[str, Any],
    *,
    status: str,
    reason: str,
) -> None:
    ensure_offer_container(state)
    ao = state["active_offer"]
    state["offer_history"].append(
        {
            "slot_start": (ao.get("slot") or {}).get("start"),
            "status": status,
            "reason": reason,
            "at": _now_utc().isoformat(),
        }
    )
    _bump_row_version(state)


def generate_public_token() -> str:
    return secrets.token_urlsafe(32)


def guard_attempts(state: dict[str, Any], max_attempts: int) -> None:
    ensure_offer_container(state)
    attempt_no = int(state["active_offer"].get("attempt_no") or 0)
    if attempt_no >= max_attempts:
        raise IntakeError("MAX_ATTEMPTS_REACHED")


# ─── Schedule Engine adapters ─────────────────────────


def _resolve_resource_id(db: Session) -> uuid.UUID:
    settings = get_settings()
    if settings.schedule_default_resource_id:
        try:
            return uuid.UUID(settings.schedule_default_resource_id)
        except ValueError:
            pass
    # Fallback: earliest active user
    user_id = (
        db.execute(select(User.id).where(User.is_active.is_(True)).order_by(User.created_at.asc()).limit(1))
        .scalars()
        .first()
    )
    if not user_id:
        raise IntakeError("NO_RESOURCE_AVAILABLE")
    return user_id


def schedule_preview_best_slot(
    db: Session,
    *,
    call_request: CallRequest,
    kind: str,
) -> SlotPreview:
    resource_id = _resolve_resource_id(db)
    now = _now_utc()

    # Start searching from tomorrow 09:00
    search_start = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    duration = timedelta(minutes=DEFAULT_INSPECTION_DURATION_MIN)

    # Find first available slot by checking existing appointments
    for day_offset in range(30):
        candidate_start = search_start + timedelta(days=day_offset)
        # Only search within business hours 09:00-17:00
        for hour_offset in range(8):
            slot_start = candidate_start.replace(hour=9 + hour_offset)
            slot_end = slot_start + duration

            overlapping = (
                db.execute(
                    select(Appointment.id).where(
                        Appointment.resource_id == resource_id,
                        Appointment.status.in_(["HELD", "CONFIRMED"]),
                        Appointment.starts_at < slot_end,
                        Appointment.ends_at > slot_start,
                    )
                )
                .scalars()
                .first()
            )
            if not overlapping:
                return SlotPreview(
                    start=slot_start,
                    end=slot_end,
                    resource_id=str(resource_id),
                )

    raise IntakeError("NO_AVAILABLE_SLOT")


def schedule_create_hold_for_call_request(
    db: Session,
    *,
    call_request: CallRequest,
    kind: str,
    slot: dict[str, Any],
    hold_minutes: int,
) -> tuple[str, datetime]:
    now = _now_utc()
    expires_at = now + timedelta(minutes=max(1, hold_minutes))

    starts_at = datetime.fromisoformat(str(slot["start"]))
    ends_at = datetime.fromisoformat(str(slot["end"]))
    resource_id = uuid.UUID(str(slot["resource_id"]))

    # App-level overlap check
    overlapping = (
        db.execute(
            select(Appointment.id).where(
                Appointment.resource_id == resource_id,
                Appointment.status.in_(["HELD", "CONFIRMED"]),
                Appointment.starts_at < ends_at,
                Appointment.ends_at > starts_at,
            )
        )
        .scalars()
        .first()
    )
    if overlapping:
        raise IntakeError("SLOT_OVERLAP")

    appt = Appointment(
        project_id=None,
        call_request_id=call_request.id,
        resource_id=resource_id,
        visit_type="PRIMARY" if kind == "INSPECTION" else kind,
        starts_at=starts_at,
        ends_at=ends_at,
        status="HELD",
        lock_level=0,
        hold_expires_at=expires_at,
        weather_class="MIXED",
        route_date=starts_at.date() if hasattr(starts_at, "date") else None,
        row_version=1,
        notes=f"EMAIL_OFFER:{kind}",
    )
    db.add(appt)
    db.flush()

    return str(appt.id), expires_at


def schedule_confirm_hold(db: Session, *, appointment_id: str) -> None:
    appt = db.get(Appointment, appointment_id)
    if not appt:
        raise IntakeError("APPOINTMENT_NOT_FOUND")
    if appt.status != "HELD":
        raise IntakeError("APPOINTMENT_NOT_HELD")

    now = _now_utc()
    appt.status = "CONFIRMED"
    appt.hold_expires_at = None
    appt.lock_level = 1
    appt.locked_at = now
    appt.lock_reason = "EMAIL_OFFER_ACCEPTED"
    appt.row_version = int(appt.row_version or 1) + 1


def schedule_cancel_hold(
    db: Session,
    *,
    appointment_id: str,
    reason: str,
) -> None:
    appt = db.get(Appointment, appointment_id)
    if not appt:
        return  # Already cancelled or missing
    if appt.status == "CANCELLED":
        return

    now = _now_utc()
    appt.status = "CANCELLED"
    appt.cancelled_at = now
    appt.cancel_reason = reason
    appt.hold_expires_at = None
    appt.row_version = int(appt.row_version or 1) + 1


# ─── Outbox adapters ──────────────────────────────────


def enqueue_offer_email(
    db: Session,
    *,
    call_request: CallRequest,
    state: dict[str, Any],
    public_token: str,
) -> None:
    ao = state.get("active_offer") or {}
    slot = ao.get("slot") or {}
    email = _questionnaire_value(state, "email") or call_request.email or ""
    address = _questionnaire_value(state, "address") or ""

    if not email:
        logger.warning("Cannot enqueue offer email: no email for cr=%s", call_request.id)
        return

    settings = get_settings()
    base_url = (settings.twilio_webhook_url or "").rstrip("/")
    confirm_url = f"{base_url}/api/v1/public/offer/{public_token}/respond"

    body_text = (
        f"Sveiki,\n\n"
        f"Siulome apziuros laika:\n"
        f"  Data/laikas: {slot.get('start', '?')}\n"
        f"  Adresas: {address}\n\n"
        f"Patvirtinti: {confirm_url}?action=accept\n"
        f"Atsisakyti: {confirm_url}?action=reject\n\n"
        f"Pagarbiai,\nVejaPRO komanda"
    )

    payload = {
        "to": email,
        "subject": "VejaPRO: Apziuros pasiulymas",
        "body_text": body_text,
        "slot_start": slot.get("start"),
        "slot_end": slot.get("end"),
        "address": address,
        "confirm_url": confirm_url,
        "token": public_token,
    }

    enqueue_notification(
        db,
        entity_type="call_request",
        entity_id=str(call_request.id),
        channel="email",
        template_key="OFFER_EMAIL",
        payload_json=payload,
    )


def enqueue_whatsapp_ping(
    db: Session,
    *,
    phone: Optional[str],
    masked_email: str,
) -> None:
    if not phone:
        return

    payload = {
        "to": phone,
        "message": (f"VejaPRO: Jums issiustas apziuros pasiulymas el. pastu ({masked_email}). Patikrinkite pasta."),
    }

    enqueue_notification(
        db,
        entity_type="call_request",
        entity_id="whatsapp_ping",
        channel="whatsapp_ping",
        template_key="WHATSAPP_OFFER_PING",
        payload_json=payload,
    )


# ─── Main orchestration functions ─────────────────────


def update_intake_and_maybe_autoprepare(
    db: Session,
    *,
    call_request: CallRequest,
    patch: dict[str, Any],
    actor: Actor,
    expected_row_version: Optional[int] = None,
) -> CallRequest:
    state = _get_intake_state(call_request)

    if expected_row_version is not None and _row_version(state) != expected_row_version:
        raise IntakeConflictError("ROW_VERSION_CONFLICT")

    state = apply_intake_patch(state, patch, source="operator", confidence=1.0)

    if questionnaire_complete(state):
        _set_phase(state, "QUESTIONNAIRE_DONE")
        try:
            slot = schedule_preview_best_slot(db, call_request=call_request, kind="INSPECTION")
            set_prepared_offer(state, "INSPECTION", slot)
        except IntakeError:
            logger.warning("Auto-prepare failed for cr=%s", call_request.id)

    _set_intake_state(call_request, state)
    db.add(call_request)

    create_audit_log(
        db,
        entity_type="call_request",
        entity_id=str(call_request.id),
        action="INTAKE_UPDATED",
        old_value=None,
        new_value={
            "patch_keys": list(patch.keys()),
            "phase": (state.get("workflow") or {}).get("phase"),
        },
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        ip_address=actor.ip_address,
        user_agent=actor.user_agent,
    )

    db.commit()
    db.refresh(call_request)
    return call_request


def prepare_offer(
    db: Session,
    *,
    call_request: CallRequest,
    kind: str,
    actor: Actor,
    expected_row_version: Optional[int] = None,
) -> CallRequest:
    state = _get_intake_state(call_request)

    if expected_row_version is not None and _row_version(state) != expected_row_version:
        raise IntakeConflictError("ROW_VERSION_CONFLICT")

    if not questionnaire_complete(state):
        raise IntakeError("QUESTIONNAIRE_INCOMPLETE")

    slot = schedule_preview_best_slot(db, call_request=call_request, kind=kind)
    set_prepared_offer(state, kind, slot)

    _set_intake_state(call_request, state)
    db.add(call_request)
    db.commit()
    db.refresh(call_request)
    return call_request


def send_offer_one_click(
    db: Session,
    *,
    call_request: CallRequest,
    actor: Actor,
    hold_minutes: Optional[int] = None,
    max_attempts: Optional[int] = None,
) -> CallRequest:
    settings = get_settings()
    if hold_minutes is None:
        hold_minutes = settings.email_hold_duration_minutes
    if max_attempts is None:
        max_attempts = settings.email_offer_max_attempts

    state = _get_intake_state(call_request)
    ensure_offer_container(state)

    if not questionnaire_complete(state):
        raise IntakeError("QUESTIONNAIRE_INCOMPLETE")

    guard_attempts(state, max_attempts)

    if state["active_offer"]["state"] != "PREPARED":
        slot = schedule_preview_best_slot(db, call_request=call_request, kind="INSPECTION")
        set_prepared_offer(state, "INSPECTION", slot)

    public_token = generate_public_token()

    appointment_id, hold_expires_at = schedule_create_hold_for_call_request(
        db,
        call_request=call_request,
        kind=state["active_offer"]["kind"],
        slot=state["active_offer"]["slot"],
        hold_minutes=hold_minutes,
    )

    set_sent_offer(
        state,
        appointment_id=appointment_id,
        hold_expires_at=hold_expires_at,
        public_token=public_token,
    )

    _set_intake_state(call_request, state)
    db.add(call_request)

    create_audit_log(
        db,
        entity_type="call_request",
        entity_id=str(call_request.id),
        action="OFFER_SENT",
        old_value=None,
        new_value={
            "appointment_id": appointment_id,
            "hold_expires_at": hold_expires_at.isoformat(),
            "attempt_no": state["active_offer"]["attempt_no"],
        },
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        ip_address=actor.ip_address,
        user_agent=actor.user_agent,
    )

    db.commit()

    # Enqueue email (separate transaction for outbox)
    enqueue_offer_email(
        db,
        call_request=call_request,
        state=state,
        public_token=public_token,
    )

    if bool((state.get("questionnaire") or {}).get("whatsapp_consent")):
        enqueue_whatsapp_ping(
            db,
            phone=_questionnaire_value(state, "phone") or call_request.phone,
            masked_email=_mask_email(_questionnaire_value(state, "email") or call_request.email or ""),
        )

    db.commit()
    db.refresh(call_request)
    return call_request


def handle_public_offer_response(
    db: Session,
    *,
    call_request: CallRequest,
    token: str,
    action: str,  # "accept" | "reject"
    suggest_text: Optional[str] = None,
) -> CallRequest:
    state = _get_intake_state(call_request)
    ensure_offer_container(state)

    expected_hash = state["active_offer"].get("token_hash")
    if not expected_hash or _sha256_hex(token) != expected_hash:
        raise IntakeError("INVALID_TOKEN")

    appointment_id = state["active_offer"].get("appointment_id")
    if not appointment_id:
        raise IntakeError("NO_ACTIVE_APPOINTMENT")

    if action == "accept":
        schedule_confirm_hold(db, appointment_id=appointment_id)
        _set_phase(state, "INSPECTION_SCHEDULED")
        append_offer_history(state, status="ACCEPTED", reason="CLIENT_ACCEPT")
        _bump_row_version(state)

        create_audit_log(
            db,
            entity_type="call_request",
            entity_id=str(call_request.id),
            action="OFFER_ACCEPTED",
            old_value=None,
            new_value={"appointment_id": appointment_id},
            actor_type="CLIENT",
            actor_id=None,
            ip_address=None,
            user_agent=None,
        )

    elif action == "reject":
        schedule_cancel_hold(db, appointment_id=appointment_id, reason="CLIENT_REJECT")
        append_offer_history(state, status="REJECTED", reason=suggest_text or "CLIENT_REJECT")

        # Instant next: prepare a new slot
        try:
            slot = schedule_preview_best_slot(db, call_request=call_request, kind=state["active_offer"]["kind"])
            set_prepared_offer(state, state["active_offer"]["kind"], slot)
        except IntakeError:
            _set_phase(state, "OFFER_REJECTED_NO_SLOTS")

        create_audit_log(
            db,
            entity_type="call_request",
            entity_id=str(call_request.id),
            action="OFFER_REJECTED",
            old_value=None,
            new_value={"reason": suggest_text or "CLIENT_REJECT"},
            actor_type="CLIENT",
            actor_id=None,
            ip_address=None,
            user_agent=None,
        )

    else:
        raise IntakeError("INVALID_ACTION")

    _set_intake_state(call_request, state)
    db.add(call_request)
    db.commit()
    db.refresh(call_request)
    return call_request
