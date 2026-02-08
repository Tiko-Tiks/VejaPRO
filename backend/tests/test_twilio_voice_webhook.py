import re

import pytest

from app.core.dependencies import SessionLocal
from app.models.project import ConversationLock


@pytest.mark.asyncio
async def test_twilio_voice_webhook_records_call_request_when_schedule_engine_disabled(client):
    # In CI we run with:
    # - ENABLE_CALL_ASSISTANT=true
    # - ENABLE_TWILIO=true
    # - ENABLE_SCHEDULE_ENGINE=false
    # - ALLOW_INSECURE_WEBHOOKS=true (so we can call webhook without Twilio signature)
    call_sid = "CA_TEST_0001"
    from_phone = "+37060000001"

    resp = await client.post(
        "/api/v1/webhook/twilio/voice",
        data={"CallSid": call_sid, "From": from_phone},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200
    assert "<Response" in resp.text

    # Should appear in admin call requests list.
    resp2 = await client.get("/api/v1/admin/call-requests?limit=50")
    assert resp2.status_code == 200
    data = resp2.json()
    items = data.get("items") or []
    assert any((it.get("source") == "voice" and it.get("notes") == call_sid) for it in items)


@pytest.mark.asyncio
async def test_twilio_voice_webhook_reprompts_existing_hold_instead_of_creating_duplicate_lock(client):
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
