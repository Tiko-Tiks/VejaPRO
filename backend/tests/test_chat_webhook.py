import uuid

import pytest


@pytest.mark.asyncio
async def test_chat_webhook_records_call_request_when_schedule_engine_disabled(client):
    conversation_id = f"chat-{uuid.uuid4()}"
    from_phone = "+37060000002"

    resp = await client.post(
        "/api/v1/webhook/chat/events",
        json={"conversation_id": conversation_id, "message": "Sveiki", "from_phone": from_phone, "name": "Jonas"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "reply" in body

    resp2 = await client.get("/api/v1/admin/call-requests?limit=50")
    assert resp2.status_code == 200
    items = resp2.json().get("items") or []
    assert any((it.get("source") == "chat" and it.get("notes") == conversation_id) for it in items)
