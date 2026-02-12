"""Email Auto-Reply — automatic responses to inbound client emails.

Type 1 (missing_data): When AI extraction didn't get all required fields,
    reply with a Lithuanian template asking for the missing info.
Type 2 (offer): When all data is collected, trigger send_offer_one_click()
    to find a slot via Schedule Engine and send an offer email.

Feature flags:
    ENABLE_EMAIL_AUTO_REPLY  — Type 1
    ENABLE_EMAIL_AUTO_OFFER  — Type 2
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.project import CallRequest
from app.services.intake_service import (
    Actor,
    _get_intake_state,
    _questionnaire_value,
    _set_intake_state,
    questionnaire_complete,
    send_offer_one_click,
)
from app.services.notification_outbox import enqueue_notification
from app.services.transition_service import create_audit_log

logger = logging.getLogger(__name__)

SYSTEM_ACTOR = Actor(actor_type="SYSTEM_EMAIL", actor_id=None, ip_address=None, user_agent=None)

NO_REPLY_PATTERN = re.compile(r"(no-?reply|noreply|mailer-daemon|postmaster)", re.IGNORECASE)

MISSING_FIELD_QUESTIONS: dict[str, str] = {
    "phone": "telefono numeris, kad galėtume su jumis susisiekti",
    "address": "paslaugos vietos adresas (gatvė, miestas)",
    "service_type": "kokios paslaugos jums reikia (pvz. vejos pjovimas, aeracija, tręšimas)",
    "area_m2": "apytikslis vejos plotas (kvadratiniais metrais)",
}

# Fields to check beyond REQUIRED_FIELDS — we also ask for phone and area_m2.
ALL_DESIRABLE_FIELDS = ("phone", "address", "service_type", "area_m2")

# Minimum interval between missing-data auto-replies (seconds).
MIN_REPLY_INTERVAL_S = 3600  # 1 hour


def _is_no_reply(email: str) -> bool:
    local_part = email.split("@")[0] if "@" in email else email
    return bool(NO_REPLY_PATTERN.search(local_part))


def _redact_email_for_log(value: str) -> str:
    raw = (value or "").strip()
    if "@" not in raw:
        return "***"
    local, domain = raw.split("@", 1)
    local_tail = local[-2:] if len(local) >= 2 else local
    return f"***{local_tail}@{domain}"


def _get_auto_reply_state(state: dict[str, Any]) -> dict[str, Any]:
    return state.setdefault("auto_replies", {})


def _get_reply_count(auto_replies: dict[str, Any], reply_type: str) -> int:
    return (auto_replies.get(reply_type) or {}).get("count", 0)


def _get_last_sent_at(auto_replies: dict[str, Any], reply_type: str) -> datetime | None:
    iso = (auto_replies.get(reply_type) or {}).get("last_sent_at")
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None


def _record_reply(auto_replies: dict[str, Any], reply_type: str) -> None:
    entry = auto_replies.setdefault(reply_type, {})
    entry["count"] = entry.get("count", 0) + 1
    entry["last_sent_at"] = datetime.now(timezone.utc).isoformat()


def _find_missing_fields(state: dict[str, Any]) -> list[str]:
    missing = []
    for field in ALL_DESIRABLE_FIELDS:
        val = _questionnaire_value(state, field)
        if not (val or "").strip():
            missing.append(field)
    return missing


def _build_missing_data_body(client_name: str, missing_fields: list[str]) -> str:
    name = client_name or "Kliente"
    questions = "\n".join(f"  - {MISSING_FIELD_QUESTIONS[f]}" for f in missing_fields if f in MISSING_FIELD_QUESTIONS)

    return (
        f"Sveiki, {name},\n"
        f"\n"
        f"Ačiū už jūsų užklausą!\n"
        f"\n"
        f"Kad galėtume paruošti jums pasiūlymą, mums dar trūksta šios informacijos:\n"
        f"{questions}\n"
        f"\n"
        f"Prašome atsakyti į šį laišką su trūkstama informacija.\n"
        f"\n"
        f"Pagarbiai,\n"
        f"VejaPRO komanda"
    )


def _build_threading_headers(state: dict[str, Any]) -> dict[str, str]:
    """Build In-Reply-To / References / Reply-To headers for email threading."""
    settings = get_settings()
    inbound = state.get("inbound_email") or {}
    headers: dict[str, str] = {}

    message_id = inbound.get("message_id")
    if message_id:
        headers["In-Reply-To"] = message_id
        headers["References"] = message_id

    if settings.cloudmailin_reply_to_address:
        headers["Reply-To"] = settings.cloudmailin_reply_to_address

    return headers


def maybe_send_auto_reply(db: Session, *, call_request: CallRequest) -> str | None:
    """Check conditions and send an auto-reply if appropriate.

    Returns:
        "missing_data" — if a missing-data reply was enqueued
        "offer_sent"   — if send_offer_one_click() was called
        None           — if no action taken
    """
    settings = get_settings()

    if not settings.enable_email_auto_reply:
        return None

    state = _get_intake_state(call_request)
    sender_email = _questionnaire_value(state, "email") or call_request.email or ""

    if not sender_email:
        return None

    if _is_no_reply(sender_email):
        logger.debug("Skipping auto-reply for no-reply address: %s", _redact_email_for_log(sender_email))
        return None

    auto_replies = _get_auto_reply_state(state)

    # --- Type 2: Auto-offer (all data collected) ---
    if questionnaire_complete(state):
        if not settings.enable_email_auto_offer:
            return None

        if _get_reply_count(auto_replies, "offer") >= 1:
            return None

        try:
            send_offer_one_click(db, call_request=call_request, actor=SYSTEM_ACTOR)
            _record_reply(auto_replies, "offer")
            _set_intake_state(call_request, state)
            db.add(call_request)
            # Note: send_offer_one_click() commits internally (2x).
            # We don't commit here — webhook handler will handle final commit.

            create_audit_log(
                db,
                entity_type="call_request",
                entity_id=str(call_request.id),
                action="EMAIL_AUTO_OFFER_SENT",
                old_value=None,
                new_value={"sender": sender_email},
                actor_type="SYSTEM_EMAIL",
                actor_id=None,
                ip_address=None,
                user_agent=None,
            )
            return "offer_sent"
        except Exception:
            logger.warning("Auto-offer failed for cr=%s", call_request.id, exc_info=True)
            return None

    # --- Type 1: Missing data reply ---
    if _get_reply_count(auto_replies, "missing_data") >= settings.email_auto_reply_max_per_cr:
        return None

    # Min interval check.
    last_sent = _get_last_sent_at(auto_replies, "missing_data")
    if last_sent:
        now = datetime.now(timezone.utc)
        last_naive = last_sent.replace(tzinfo=None) if last_sent.tzinfo else last_sent
        now_naive = now.replace(tzinfo=None)
        elapsed = (now_naive - last_naive).total_seconds()
        if elapsed < MIN_REPLY_INTERVAL_S:
            return None

    missing = _find_missing_fields(state)
    if not missing:
        return None

    client_name = _questionnaire_value(state, "client_name") or call_request.name or ""
    body_text = _build_missing_data_body(client_name, missing)
    subject = "Re: " + ((state.get("inbound_email") or {}).get("subject") or "Jūsų užklausa")
    extra_headers = _build_threading_headers(state)

    payload: dict[str, Any] = {
        "to": sender_email,
        "subject": subject,
        "body_text": body_text,
    }
    if extra_headers:
        payload["extra_headers"] = extra_headers

    enqueue_notification(
        db,
        entity_type="call_request",
        entity_id=str(call_request.id),
        channel="email",
        template_key="EMAIL_AUTO_REPLY_MISSING_DATA",
        payload_json=payload,
    )

    _record_reply(auto_replies, "missing_data")
    _set_intake_state(call_request, state)
    db.add(call_request)

    create_audit_log(
        db,
        entity_type="call_request",
        entity_id=str(call_request.id),
        action="EMAIL_AUTO_REPLY_MISSING_DATA",
        old_value=None,
        new_value={"sender": sender_email, "missing_fields": missing},
        actor_type="SYSTEM_EMAIL",
        actor_id=None,
        ip_address=None,
        user_agent=None,
    )

    return "missing_data"
