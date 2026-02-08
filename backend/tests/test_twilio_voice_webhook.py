import re
from uuid import UUID

import pytest

from app.core.dependencies import SessionLocal
from app.models.project import CallRequest, ConversationLock, User


def _ensure_user(user_id: str, role: str = "SUBCONTRACTOR") -> None:
    """Seed at least one active operator user so Voice webhook can pick a default resource."""
    assert SessionLocal is not None
    user_uuid = UUID(user_id)
    with SessionLocal() as db:
        if db.get(User, user_uuid):
            return
        db.add(
            User(
                id=user_uuid,
                email=f"{user_uuid}@test.local",
                phone=None,
                role=role,
                is_active=True,
            )
        )
        db.commit()


@pytest.mark.asyncio
async def test_twilio_voice_webhook_records_call_request_when_schedule_engine_disabled(client):
    _ensure_user("00000000-0000-0000-0000-000000000010", role="SUBCONTRACTOR")
    call_sid = "CA_TEST_0001"
    from_phone = "+37060000001"

    resp = await client.post(
        "/api/v1/webhook/twilio/voice",
        data={"CallSid": call_sid, "From": from_phone},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200
    assert "<Response" in resp.text

    assert SessionLocal is not None
    with SessionLocal() as db:
        row = (
            db.query(CallRequest)
            .filter(
                CallRequest.source == "voice",
                CallRequest.notes == call_sid,
            )
            .one_or_none()
        )
        assert row is not None


@pytest.mark.asyncio
async def test_twilio_voice_webhook_reprompts_existing_hold_instead_of_creating_duplicate_lock(client):
    _ensure_user("00000000-0000-0000-0000-000000000011", role="SUBCONTRACTOR")
    call_sid = "CA_TEST_REPROMPT_0001"
    from_phone = "+37060000003"

    resp1 = await client.post(
        "/api/v1/webhook/twilio/voice",
        data={"CallSid": call_sid, "From": from_phone},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp1.status_code == 200
    m = re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", resp1.text)
    assert m, resp1.text
    slot_text = m.group(0)

    # Same webhook again (e.g. retry / no DTMF yet): should re-prompt the same slot, not create a new lock.
    resp2 = await client.post(
        "/api/v1/webhook/twilio/voice",
        data={"CallSid": call_sid, "From": from_phone},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp2.status_code == 200
    assert slot_text in resp2.text

    assert SessionLocal is not None
    with SessionLocal() as db:
        count = (
            db.query(ConversationLock)
            .filter(
                ConversationLock.channel == "VOICE",
                ConversationLock.conversation_id == call_sid,
            )
            .count()
        )
        assert count == 1
