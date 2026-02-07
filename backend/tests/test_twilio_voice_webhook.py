import pytest


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

