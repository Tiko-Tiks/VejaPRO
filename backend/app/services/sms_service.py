import logging

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def send_sms(to_number: str, body: str) -> str:
    """Send an SMS via Twilio. Returns the message SID on success."""
    settings = get_settings()
    if not settings.twilio_account_sid or not settings.twilio_auth_token or not settings.twilio_from_number:
        raise RuntimeError("Twilio is not configured")

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    try:
        message = client.messages.create(
            to=to_number,
            from_=settings.twilio_from_number,
            body=body,
        )
        logger.info("SMS sent to=%s sid=%s", to_number, message.sid)
        return message.sid
    except TwilioRestException:
        logger.exception("Twilio API error sending SMS to=%s", to_number)
        raise
    except Exception:
        logger.exception("Unexpected error sending SMS to=%s", to_number)
        raise
