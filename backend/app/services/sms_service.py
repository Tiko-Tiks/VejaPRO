from twilio.rest import Client

from app.core.config import get_settings


def send_sms(to_number: str, body: str) -> None:
    settings = get_settings()
    if not settings.twilio_account_sid or not settings.twilio_auth_token or not settings.twilio_from_number:
        raise RuntimeError("Twilio is not configured")

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    client.messages.create(
        to=to_number,
        from_=settings.twilio_from_number,
        body=body,
    )
