import uuid

import pytest

from app.core.dependencies import SessionLocal
from app.models.project import ConversationLock


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


@pytest.mark.asyncio
async def test_chat_webhook_reprompts_existing_hold_instead_of_creating_duplicate_lock(client):
    conversation_id = f"chat-{uuid.uuid4()}"

    first = await client.post(
        "/api/v1/webhook/chat/events",
        json={"conversation_id": conversation_id, "message": "Sveiki", "from_phone": "+37060000002", "name": "Jonas"},
    )
    assert first.status_code == 200, first.text
    body1 = first.json()
    assert body1.get("state", {}).get("status") == "held"
    starts_at_1 = body1.get("state", {}).get("starts_at")
    assert starts_at_1

    # Send a non-confirm/non-cancel message: should re-prompt the same held slot (idempotent behavior).
    second = await client.post(
        "/api/v1/webhook/chat/events",
        json={"conversation_id": conversation_id, "message": "?", "from_phone": "+37060000002", "name": "Jonas"},
    )
    assert second.status_code == 200, second.text
    body2 = second.json()
    assert body2.get("state", {}).get("status") == "held"
    assert body2.get("state", {}).get("starts_at") == starts_at_1

    assert SessionLocal is not None
    with SessionLocal() as db:
        count = (
            db.query(ConversationLock)
            .filter(
                ConversationLock.channel == "CHAT",
                ConversationLock.conversation_id == conversation_id,
            )
            .count()
        )
        assert count == 1
