"""
V2.3 Notification Outbox — Multi-channel dispatch

Supports: email (.ics) — primary, whatsapp_ping (Twilio WhatsApp API) — secondary, SMS disabled.
"""

from __future__ import annotations

import base64
import logging
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    user: Optional[str]
    password: Optional[str]
    use_tls: bool
    from_email: str


def build_ics_invite(
    *,
    summary: str,
    starts_at_utc: datetime,
    ends_at_utc: datetime,
    location: str,
) -> bytes:
    uid = f"{uuid4()}@vejapro"
    dtstamp = starts_at_utc.strftime("%Y%m%dT%H%M%SZ")
    dtstart = starts_at_utc.strftime("%Y%m%dT%H%M%SZ")
    dtend = ends_at_utc.strftime("%Y%m%dT%H%M%SZ")

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//VejaPRO//Unified Client Card//LT\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:REQUEST\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTAMP:{dtstamp}\r\n"
        f"DTSTART:{dtstart}\r\n"
        f"DTEND:{dtend}\r\n"
        f"SUMMARY:{summary}\r\n"
        f"LOCATION:{location}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    return ics.encode("utf-8")


def send_email_via_smtp(
    *,
    smtp: SmtpConfig,
    to_email: str,
    subject: str,
    body_text: str,
    ics_bytes: Optional[bytes] = None,
    extra_headers: dict[str, str] | None = None,
) -> None:
    msg = EmailMessage()
    msg["From"] = smtp.from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body_text)

    if extra_headers:
        for header_name, header_value in extra_headers.items():
            msg[header_name] = header_value

    if ics_bytes:
        msg.add_attachment(
            ics_bytes,
            maintype="text",
            subtype="calendar",
            filename="invite.ics",
            params={"method": "REQUEST"},
        )

    import ssl

    context = ssl.create_default_context()

    # Port 465 uses implicit SSL (SMTP_SSL), port 587 uses STARTTLS
    if smtp.port == 465:
        server = smtplib.SMTP_SSL(smtp.host, smtp.port, timeout=20, context=context)
    else:
        server = smtplib.SMTP(smtp.host, smtp.port, timeout=20)
        if smtp.use_tls:
            server.starttls(context=context)
    try:
        if smtp.user and smtp.password:
            server.login(smtp.user, smtp.password)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            # SMTP cleanup can fail; safe to ignore
            pass


def build_offer_email_payload(
    *,
    to_email: str,
    subject: str,
    body_text: str,
    ics_bytes: Optional[bytes],
) -> dict[str, Any]:
    attachments: list[dict[str, Any]] = []
    if ics_bytes:
        attachments.append(
            {
                "filename": "invite.ics",
                "mime": "text/calendar",
                "content_b64": base64.b64encode(ics_bytes).decode("ascii"),
            }
        )

    return {
        "to": to_email,
        "subject": subject,
        "body_text": body_text,
        "attachments": attachments,
    }


def build_whatsapp_ping_payload(*, phone: str, message: str) -> dict[str, Any]:
    return {"to": phone, "message": message}


def send_whatsapp_via_twilio(
    payload: dict[str, Any],
    *,
    account_sid: str,
    auth_token: str,
    from_number: str,
) -> None:
    """Send a WhatsApp message via Twilio WhatsApp API.

    ``from_number`` should already include the ``whatsapp:`` prefix
    (e.g. ``whatsapp:+14155238886`` for Sandbox).
    """
    if not from_number:
        raise RuntimeError("WHATSAPP_FROM_NUMBER_NOT_CONFIGURED")

    from twilio.rest import Client  # lazy import — only needed when actually sending

    to_phone = str(payload.get("to") or "").strip()
    message = str(payload.get("message") or "").strip()
    if not to_phone or not message:
        raise RuntimeError("WHATSAPP_MISSING_FIELDS")

    # Ensure whatsapp: prefix on both numbers
    if not to_phone.startswith("whatsapp:"):
        to_phone = f"whatsapp:{to_phone}"
    if not from_number.startswith("whatsapp:"):
        from_number = f"whatsapp:{from_number}"

    client = Client(account_sid, auth_token)
    client.messages.create(to=to_phone, from_=from_number, body=message)
    logger.info("WhatsApp sent: to=%s", to_phone)


def outbox_channel_send(
    *,
    channel: str,
    payload: dict[str, Any],
    smtp: Optional[SmtpConfig] = None,
    enable_whatsapp: bool = False,
    twilio_account_sid: str = "",
    twilio_auth_token: str = "",
    twilio_whatsapp_from_number: str = "",
) -> None:
    if channel == "email":
        if smtp is None:
            raise RuntimeError("SMTP_NOT_CONFIGURED")

        to_email = payload["to"]
        subject = payload["subject"]
        body_text = payload["body_text"]

        # Reconstruct ICS from attachment if present
        ics_bytes = None
        attachments = payload.get("attachments") or []
        for a in attachments:
            if a.get("filename") == "invite.ics" and a.get("content_b64"):
                ics_bytes = base64.b64decode(a["content_b64"])
                break

        # Build ICS from slot data if not in attachments but slot info available
        if ics_bytes is None and payload.get("slot_start") and payload.get("slot_end"):
            try:
                starts_at = datetime.fromisoformat(str(payload["slot_start"]))
                ends_at = datetime.fromisoformat(str(payload["slot_end"]))
                ics_bytes = build_ics_invite(
                    summary="VejaPRO Apziura",
                    starts_at_utc=starts_at,
                    ends_at_utc=ends_at,
                    location=payload.get("address") or "",
                )
            except (ValueError, TypeError):
                logger.warning("Failed to build ICS from slot data")

        send_email_via_smtp(
            smtp=smtp,
            to_email=to_email,
            subject=subject,
            body_text=body_text,
            ics_bytes=ics_bytes,
            extra_headers=payload.get("extra_headers"),
        )
        return

    if channel == "whatsapp_ping":
        if not enable_whatsapp:
            return
        send_whatsapp_via_twilio(
            payload,
            account_sid=twilio_account_sid,
            auth_token=twilio_auth_token,
            from_number=twilio_whatsapp_from_number,
        )
        return

    if channel == "sms":
        # V2.2: SMS remains supported via legacy Twilio path.
        # This function is only for new channels; SMS goes through sms_service.send_sms().
        raise RuntimeError("SMS_USE_LEGACY_PATH")

    raise RuntimeError(f"UNKNOWN_CHANNEL:{channel}")
