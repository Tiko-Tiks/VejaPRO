"""CloudMailin inbound email webhook — receive emails, create CallRequest, AI extraction."""

from __future__ import annotations

import base64
import hmac
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import get_db
from app.models.project import CallRequest
from app.schemas.assistant import CallRequestStatus
from app.services.intake_service import _get_intake_state, _set_intake_state, merge_ai_suggestions
from app.services.transition_service import create_audit_log
from app.utils.rate_limit import get_client_ip, get_user_agent, rate_limiter

router = APIRouter()
logger = logging.getLogger(__name__)
SYSTEM_ENTITY_ID = "00000000-0000-0000-0000-000000000000"


def _ensure_email_webhook_enabled() -> None:
    settings = get_settings()
    if not settings.enable_email_webhook:
        raise HTTPException(404, "Nerastas")
    if not settings.cloudmailin_username or not settings.cloudmailin_password:
        raise HTTPException(500, "Nesukonfigūruotas CloudMailin webhook autentifikavimas")


def verify_basic_auth(request: Request, expected_user: str, expected_pass: str) -> bool:
    """Verify HTTP Basic Auth credentials from CloudMailin webhook."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth[6:], validate=True).decode("utf-8")
        user, password = decoded.split(":", 1)
        return hmac.compare_digest(user, expected_user) and hmac.compare_digest(password, expected_pass)
    except Exception:
        return False


def _parse_from_name(from_header: str) -> str:
    """Extract display name from 'Name <email>' format."""
    if not from_header:
        return ""
    # Match: "Jonas Petraitis <jonas@example.lt>"
    match = re.match(r"^(.+?)\s*<[^>]+>$", from_header.strip())
    if match:
        name = match.group(1).strip().strip("\"'")
        return name
    return ""


def _find_existing_by_message_id(db: Session, message_id: str) -> CallRequest | None:
    """Check if an email with this Message-Id was already processed (idempotency)."""
    settings = get_settings()
    if not (settings.database_url or "").startswith("sqlite"):
        from sqlalchemy import text

        stmt = text(
            "SELECT id FROM call_requests "
            "WHERE source = 'email' "
            "AND intake_state->'inbound_email'->>'message_id' = :mid "
            "LIMIT 1"
        )
        row = db.execute(stmt, {"mid": message_id}).first()
        if row:
            return db.get(CallRequest, row[0])
        return None

    # SQLite fallback: scan (OK for tests).
    rows = db.execute(select(CallRequest).where(CallRequest.source == "email")).scalars().all()
    for cr in rows:
        state = cr.intake_state or {}
        inbound = state.get("inbound_email") or {}
        if inbound.get("message_id") == message_id:
            return cr
    return None


def _find_existing_cr_by_sender(db: Session, sender_email: str) -> CallRequest | None:
    """Find an existing NEW email CallRequest from the same sender (conversation tracking)."""
    return (
        db.execute(
            select(CallRequest)
            .where(
                CallRequest.source == "email",
                CallRequest.email == sender_email,
                CallRequest.status.in_(["NEW"]),
            )
            .order_by(CallRequest.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


@router.post("/webhook/email/inbound")
async def email_inbound_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Receive inbound email from CloudMailin and create a CallRequest with AI extraction."""
    _ensure_email_webhook_enabled()
    settings = get_settings()

    # --- Rate limit by IP ---
    ip = get_client_ip(request) or "unknown"
    allowed, _ = rate_limiter.allow(
        f"email_webhook:ip:{ip}",
        settings.rate_limit_email_webhook_ip_per_min,
        60,
    )
    if not allowed:
        raise HTTPException(429, "Too Many Requests")

    # --- Basic Auth verification (CloudMailin sends credentials in URL → Authorization header) ---
    if not verify_basic_auth(request, settings.cloudmailin_username, settings.cloudmailin_password):
        create_audit_log(
            db,
            entity_type="system",
            entity_id=SYSTEM_ENTITY_ID,
            action="EMAIL_WEBHOOK_AUTH_INVALID",
            old_value=None,
            new_value=None,
            actor_type="SYSTEM",
            actor_id=None,
            ip_address=ip,
            user_agent=get_user_agent(request),
        )
        db.commit()
        raise HTTPException(403, "Neteisingi prisijungimo duomenys")

    # --- Parse JSON from CloudMailin ---
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, "Neteisingas JSON formatas") from exc

    envelope = body.get("envelope") or {}
    headers = body.get("headers") or {}
    plain_text = str(body.get("plain") or "").strip()
    reply_plain = str(body.get("reply_plain") or "").strip()

    sender = str(envelope.get("from") or "").strip()
    from_header = str(headers.get("from") or "").strip()
    subject = str(headers.get("subject") or "").strip()
    message_id = str(headers.get("message_id") or "").strip()
    recipient = str(envelope.get("to") or "").strip()

    # --- Rate limit by sender ---
    if sender:
        allowed_sender, _ = rate_limiter.allow(
            f"email_webhook:sender:{sender.lower()}",
            settings.rate_limit_email_webhook_sender_per_min,
            60,
        )
        if not allowed_sender:
            raise HTTPException(429, "Too Many Requests")

    # --- Idempotency: skip duplicate Message-Id ---
    if message_id:
        existing = _find_existing_by_message_id(db, message_id)
        if existing:
            logger.info("Duplicate email Message-Id=%s — skipping", message_id)
            return {"status": "duplicate", "call_request_id": str(existing.id)}

    # --- Parse email data ---
    from_name = _parse_from_name(from_header) or _parse_from_name(sender)
    from_email = sender
    body_text = reply_plain or plain_text

    # --- Conversation tracking: merge reply into existing CR ---
    is_reply = False
    existing_cr = None
    if settings.enable_email_auto_reply and from_email:
        existing_cr = _find_existing_cr_by_sender(db, from_email)

    if existing_cr:
        cr = existing_cr
        is_reply = True

        # Append new reply text to notes.
        reply_note = ""
        if subject:
            reply_note += f"Tema: {subject}\n"
        if body_text:
            reply_note += body_text[:5000]
        if reply_note:
            cr.notes = (
                (cr.notes or "")
                + f"\n\n--- Reply ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}) ---\n"
                + reply_note
            )

        # Update inbound_email metadata with latest message.
        state = _get_intake_state(cr)
        state["inbound_email"] = {
            "message_id": message_id,
            "from": from_header or sender,
            "subject": subject,
            "recipient": recipient,
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
        _set_intake_state(cr, state)
        db.add(cr)
        db.flush()
    else:
        # Build notes from subject + body.
        notes_parts = []
        if subject:
            notes_parts.append(f"Tema: {subject}")
        if body_text:
            notes_parts.append(body_text[:5000])
        notes = "\n".join(notes_parts) if notes_parts else ""

        # --- Create CallRequest ---
        cr = CallRequest(
            name=from_name or from_email or "Nežinomas",
            phone="",
            email=from_email,
            notes=notes,
            status=CallRequestStatus.NEW.value,
            source="email",
            intake_state={},
        )
        db.add(cr)
        db.flush()

        # --- Populate intake_state with email header data ---
        state = _get_intake_state(cr)
        q = state.setdefault("questionnaire", {})

        # Email from envelope is 100% reliable.
        if from_email:
            q["email"] = {"value": from_email, "source": "email", "confidence": 1.0}

        # Name from From header is very reliable.
        if from_name:
            q["client_name"] = {"value": from_name, "source": "email", "confidence": 0.9}

        # Store inbound email metadata for idempotency + traceability.
        state["inbound_email"] = {
            "message_id": message_id,
            "from": from_header or sender,
            "subject": subject,
            "recipient": recipient,
            "received_at": datetime.now(timezone.utc).isoformat(),
        }

        _set_intake_state(cr, state)
        db.add(cr)

    # --- AI Conversation Extract (non-blocking) ---
    if settings.enable_ai_conversation_extract and body_text:
        try:
            from app.services.ai.conversation_extract.service import extract_conversation_data

            extract_result = await extract_conversation_data(
                body_text,
                db,
                call_request_id=str(cr.id),
            )
            suggestions = extract_result.extract_result.to_suggestions_dict()
            if suggestions:
                state = _get_intake_state(cr)
                state = merge_ai_suggestions(
                    state, suggestions, min_confidence=settings.ai_conversation_extract_min_confidence
                )
                _set_intake_state(cr, state)
                db.add(cr)
        except Exception:
            logger.warning("AI extraction failed for email Message-Id=%s — continuing", message_id)

    # --- AI Sentiment Classification (non-blocking) ---
    if settings.enable_ai_email_sentiment and body_text:
        try:
            from app.services.ai.sentiment.service import classify_email_sentiment

            await classify_email_sentiment(
                body_text,
                db,
                call_request_id=str(cr.id),
                message_id=message_id,
            )
        except Exception:
            logger.warning("Sentiment failed for cr=%s — continuing", cr.id)

    # --- Auto-reply (non-blocking) ---
    auto_reply_result = None
    if settings.enable_email_auto_reply:
        try:
            from app.services.email_auto_reply import maybe_send_auto_reply

            auto_reply_result = maybe_send_auto_reply(db, call_request=cr)
            if auto_reply_result:
                logger.info("Auto-reply '%s' for cr=%s", auto_reply_result, cr.id)
        except Exception:
            logger.warning("Auto-reply failed for cr=%s — continuing", cr.id, exc_info=True)

    # --- Audit log ---
    audit_action = "EMAIL_REPLY_MERGED" if is_reply else "EMAIL_INBOUND_RECEIVED"
    create_audit_log(
        db,
        entity_type="call_request",
        entity_id=str(cr.id),
        action=audit_action,
        old_value=None,
        new_value={"source": "email", "email": sender, "subject": subject},
        actor_type="SYSTEM_EMAIL",
        actor_id=None,
        ip_address=ip,
        user_agent=get_user_agent(request),
        metadata={
            "message_id": message_id,
            "recipient": recipient,
            "body_length": len(body_text),
            "is_reply": is_reply,
            "auto_reply": auto_reply_result,
        },
    )

    db.commit()
    db.refresh(cr)

    status = "reply_merged" if is_reply else "ok"
    return {"status": status, "call_request_id": str(cr.id)}
