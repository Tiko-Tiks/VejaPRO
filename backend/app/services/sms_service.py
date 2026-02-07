import logging

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _redact_phone(value: str) -> str:
    if not value:
        return ""
    # Keep last 3 digits for operator traceability; mask the rest.
    tail = value[-3:] if len(value) >= 3 else value
    return f"***{tail}"


def send_sms(to_number: str, body: str) -> str:
    """Send an SMS via Twilio. Returns the message SID on success."""
    settings = get_settings()
    if not settings.twilio_account_sid or not settings.twilio_auth_token or not settings.twilio_from_number:
        raise RuntimeError("Nesukonfigūruotas Twilio")

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    log_to = _redact_phone(to_number) if settings.pii_redaction_enabled else to_number
    try:
        message = client.messages.create(
            to=to_number,
            from_=settings.twilio_from_number,
            body=body,
        )
        logger.info("SMS sent to=%s sid=%s", log_to, message.sid)
        return message.sid
    except TwilioRestException:
        logger.exception("Twilio API error sending SMS to=%s", log_to)
        raise
    except Exception:
        logger.exception("Unexpected error sending SMS to=%s", log_to)
        raise
