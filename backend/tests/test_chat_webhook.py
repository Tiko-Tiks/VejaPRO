import uuid
from uuid import UUID

import pytest

from app.core.dependencies import SessionLocal
from app.models.project import Appointment, CallRequest, ConversationLock, User


def _ensure_user(user_id: str, role: str = "SUBCONTRACTOR") -> None:
    """Seed at least one active user so webhook scheduling can pick a default resource.

    These webhook tests run integration-style (separate uvicorn process in CI), so we seed the DB directly.
    """
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
async def test_chat_webhook_records_call_request_when_schedule_engine_disabled(client):
    _ensure_user("00000000-0000-0000-0000-000000000010")
    conversation_id = f"chat-{uuid.uuid4()}"
    from_phone = "+37060000002"

    resp = await client.post(
        "/api/v1/webhook/chat/events",
        json={"conversation_id": conversation_id, "message": "Sveiki", "from_phone": from_phone, "name": "Jonas"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "reply" in body

    assert SessionLocal is not None
    with SessionLocal() as db:
        row = (
            db.query(CallRequest)
            .filter(
                CallRequest.source == "chat",
                CallRequest.notes == conversation_id,
            )
            .one_or_none()
        )
        assert row is not None


@pytest.mark.asyncio
async def test_chat_webhook_reprompts_existing_hold_instead_of_creating_duplicate_lock(client):
    _ensure_user("00000000-0000-0000-0000-000000000011")
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


@pytest.mark.asyncio
async def test_chat_webhook_takes_over_existing_hold_for_same_phone_across_conversations(client):
    _ensure_user("00000000-0000-0000-0000-000000000012")
    phone = f"+3706{uuid.uuid4().int % 10**7:07d}"
    conversation_id_1 = f"chat-{uuid.uuid4()}"
    conversation_id_2 = f"chat-{uuid.uuid4()}"

    first = await client.post(
        "/api/v1/webhook/chat/events",
        json={"conversation_id": conversation_id_1, "message": "Sveiki", "from_phone": phone, "name": "Jonas"},
    )
    assert first.status_code == 200, first.text
    body1 = first.json()
    assert body1.get("state", {}).get("status") == "held"
    starts_at_1 = body1.get("state", {}).get("starts_at")
    assert starts_at_1

    second = await client.post(
        "/api/v1/webhook/chat/events",
        json={"conversation_id": conversation_id_2, "message": "Sveiki", "from_phone": phone, "name": "Jonas"},
    )
    assert second.status_code == 200, second.text
    body2 = second.json()
    assert body2.get("state", {}).get("status") == "held"
    assert body2.get("state", {}).get("starts_at") == starts_at_1

    assert SessionLocal is not None
    with SessionLocal() as db:
        count_1 = (
            db.query(ConversationLock)
            .filter(
                ConversationLock.channel == "CHAT",
                ConversationLock.conversation_id == conversation_id_1,
            )
            .count()
        )
        count_2 = (
            db.query(ConversationLock)
            .filter(
                ConversationLock.channel == "CHAT",
                ConversationLock.conversation_id == conversation_id_2,
            )
            .count()
        )
        assert count_1 == 0
        assert count_2 == 1

        held_count = (
            db.query(Appointment)
            .join(CallRequest, Appointment.call_request_id == CallRequest.id)
            .filter(
                CallRequest.phone == phone,
                Appointment.status == "HELD",
            )
            .count()
        )
        assert held_count == 1
