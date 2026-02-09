"""
V2.2 Notification Outbox — Multi-channel dispatch

Supports: email (.ics), whatsapp_ping (stub), SMS disabled.
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
) -> None:
    msg = EmailMessage()
    msg["From"] = smtp.from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body_text)

    if ics_bytes:
        msg.add_attachment(
            ics_bytes,
            maintype="text",
            subtype="calendar",
            filename="invite.ics",
            params={"method": "REQUEST"},
        )

    server = smtplib.SMTP(smtp.host, smtp.port, timeout=20)
    try:
        if smtp.use_tls:
            server.starttls()
        if smtp.user and smtp.password:
            server.login(smtp.user, smtp.password)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
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


def send_whatsapp_ping_stub(payload: dict[str, Any]) -> None:
    logger.info("WhatsApp ping stub: to=%s (not sent)", payload.get("to"))


def outbox_channel_send(
    *,
    channel: str,
    payload: dict[str, Any],
    smtp: Optional[SmtpConfig] = None,
    enable_whatsapp: bool = False,
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
        )
        return

    if channel == "whatsapp_ping":
        if not enable_whatsapp:
            return
        send_whatsapp_ping_stub(payload)
        return

    if channel == "sms":
        # V2.2: SMS remains supported via legacy Twilio path.
        # This function is only for new channels; SMS goes through sms_service.send_sms().
        raise RuntimeError("SMS_USE_LEGACY_PATH")

    raise RuntimeError(f"UNKNOWN_CHANNEL:{channel}")
