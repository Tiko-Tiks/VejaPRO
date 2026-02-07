from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.dependencies import SessionLocal
from app.models.project import Appointment, ConversationLock, SchedulePreview, User


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _mint_token(role: str) -> str:
    secret = os.getenv("SUPABASE_JWT_SECRET", "")
    if not secret:
        raise RuntimeError("SUPABASE_JWT_SECRET is required for tests")
    payload = {
        "sub": "00000000-0000-0000-0000-000000000002",
        "email": "role-tests@example.com",
        "app_metadata": {"role": role},
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        "aud": os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated"),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


def _ensure_user(user_id: str, role: str = "SUBCONTRACTOR") -> None:
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


@pytest_asyncio.fixture
async def subcontractor_client() -> AsyncClient:
    # Separate client with SUBCONTRACTOR role to exercise lock_level>=2 restrictions.
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:8000")
    token = _mint_token("SUBCONTRACTOR")
    async with AsyncClient(
        base_url=base_url,
        headers={"Authorization": f"Bearer {token}"},
    ) as c:
        yield c


def _skip_if_disabled(resp_status: int) -> None:
    if resp_status == 404:
        pytest.skip("Schedule Engine is disabled (ENABLE_SCHEDULE_ENGINE=false)")


async def _create_project(client: AsyncClient) -> str:
    r = await client.post("/api/v1/projects", json={"name": "Test Project"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_hold_lifecycle_confirm_success(client: AsyncClient):
    project_id = await _create_project(client)
    starts_at = _now() + timedelta(hours=1)
    ends_at = starts_at + timedelta(minutes=30)
    _ensure_user("00000000-0000-0000-0000-000000000010")

    create = await client.post(
        "/api/v1/admin/schedule/holds",
        json={
            "channel": "VOICE",
            "conversation_id": "conv-hold-1",
            "resource_id": "00000000-0000-0000-0000-000000000010",
            "visit_type": "PRIMARY",
            "project_id": project_id,
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
            "weather_class": "MIXED",
        },
    )
    _skip_if_disabled(create.status_code)
    assert create.status_code == 201, create.text
    appt_id = create.json()["appointment_id"]

    confirm = await client.post(
        "/api/v1/admin/schedule/holds/confirm",
        json={"channel": "VOICE", "conversation_id": "conv-hold-1"},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["appointment_id"] == appt_id
    assert confirm.json()["status"] == "CONFIRMED"

    # Lock should be deleted; confirming again should fail.
    confirm2 = await client.post(
        "/api/v1/admin/schedule/holds/confirm",
        json={"channel": "VOICE", "conversation_id": "conv-hold-1"},
    )
    assert confirm2.status_code in (404, 409), confirm2.text


@pytest.mark.asyncio
async def test_hold_unique_conversation_lock(client: AsyncClient):
    project_id = await _create_project(client)
    starts_at = _now() + timedelta(hours=2)
    ends_at = starts_at + timedelta(minutes=30)
    _ensure_user("00000000-0000-0000-0000-000000000011")

    first = await client.post(
        "/api/v1/admin/schedule/holds",
        json={
            "channel": "CHAT",
            "conversation_id": "conv-uniq-1",
            "resource_id": "00000000-0000-0000-0000-000000000011",
            "project_id": project_id,
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
        },
    )
    _skip_if_disabled(first.status_code)
    assert first.status_code == 201, first.text

    second = await client.post(
        "/api/v1/admin/schedule/holds",
        json={
            "channel": "CHAT",
            "conversation_id": "conv-uniq-1",
            "resource_id": "00000000-0000-0000-0000-000000000011",
            "project_id": project_id,
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
        },
    )
    assert second.status_code == 409, second.text


@pytest.mark.asyncio
async def test_hold_expire_cancels_expired(client: AsyncClient):
    project_id = await _create_project(client)
    starts_at = _now() + timedelta(hours=3)
    ends_at = starts_at + timedelta(minutes=30)
    _ensure_user("00000000-0000-0000-0000-000000000012")

    create = await client.post(
        "/api/v1/admin/schedule/holds",
        json={
            "channel": "VOICE",
            "conversation_id": "conv-expire-1",
            "resource_id": "00000000-0000-0000-0000-000000000012",
            "project_id": project_id,
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
        },
    )
    _skip_if_disabled(create.status_code)
    assert create.status_code == 201, create.text
    appt_id = create.json()["appointment_id"]

    # Force expiry in DB (worker endpoint is called manually in Phase 2).
    assert SessionLocal is not None
    with SessionLocal() as db:
        appt = db.get(Appointment, appt_id)
        assert appt is not None
        appt.hold_expires_at = _now() - timedelta(seconds=1)
        lock = (
            db.query(ConversationLock)
            .filter(ConversationLock.conversation_id == "conv-expire-1")
            .one()
        )
        lock.hold_expires_at = appt.hold_expires_at
        db.commit()

    expire = await client.post("/api/v1/admin/schedule/holds/expire")
    assert expire.status_code == 200, expire.text
    assert expire.json()["expired_count"] >= 1

    with SessionLocal() as db:
        appt = db.get(Appointment, appt_id)
        assert appt is not None
        assert appt.status == "CANCELLED"
        assert appt.cancel_reason == "HOLD_EXPIRED"


@pytest.mark.asyncio
async def test_reschedule_preview_and_confirm_happy_path(client: AsyncClient):
    project_id = await _create_project(client)
    route_date = (_now() + timedelta(days=1)).date()
    resource_id = "00000000-0000-0000-0000-000000000020"
    _ensure_user(resource_id)

    # Create two CONFIRMED appointments via hold->confirm so they have resource_id populated.
    for i in range(2):
        starts_at = datetime(route_date.year, route_date.month, route_date.day, 9 + i, 0, tzinfo=timezone.utc)
        ends_at = starts_at + timedelta(minutes=30)
        conv_id = f"conv-res-{i}"
        r = await client.post(
            "/api/v1/admin/schedule/holds",
            json={
                "channel": "VOICE",
                "conversation_id": conv_id,
                "resource_id": resource_id,
                "project_id": project_id,
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat(),
            },
        )
        _skip_if_disabled(r.status_code)
        assert r.status_code == 201, r.text
        rc = await client.post(
            "/api/v1/admin/schedule/holds/confirm",
            json={"channel": "VOICE", "conversation_id": conv_id},
        )
        assert rc.status_code == 200, rc.text

    preview = await client.post(
        "/api/v1/admin/schedule/reschedule/preview",
        json={
            "route_date": route_date.isoformat(),
            "resource_id": resource_id,
            "scope": "DAY",
            "reason": "WEATHER",
            "comment": "Test",
            "rules": {"preserve_locked_level": 2, "allow_replace_with_weather_resistant": True},
        },
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["original_appointment_ids"]
    assert body["suggested_actions"]
    assert body["summary"]["cancel_count"] >= 1
    assert body["summary"]["create_count"] >= 1

    confirm = await client.post(
        "/api/v1/admin/schedule/reschedule/confirm",
        json={
            "preview_id": body["preview_id"],
            "preview_hash": body["preview_hash"],
            "reason": "WEATHER",
            "comment": "Confirmed",
            "expected_versions": body["expected_versions"],
        },
    )
    assert confirm.status_code == 200, confirm.text
    out = confirm.json()
    assert out["success"] is True
    assert len(out["new_appointment_ids"]) >= 1

    # Originals cancelled, new rows confirmed, and superseded chain written.
    assert SessionLocal is not None
    with SessionLocal() as db:
        for original_id in body["original_appointment_ids"]:
            old = db.get(Appointment, original_id)
            assert old is not None
            assert old.status == "CANCELLED"
            assert old.superseded_by_id is not None

        new0 = db.get(Appointment, out["new_appointment_ids"][0])
        assert new0 is not None
        assert new0.status == "CONFIRMED"


@pytest.mark.asyncio
async def test_reschedule_confirm_hash_mismatch_409(client: AsyncClient):
    project_id = await _create_project(client)
    route_date = (_now() + timedelta(days=2)).date()
    resource_id = "00000000-0000-0000-0000-000000000021"
    _ensure_user(resource_id)

    starts_at = datetime(route_date.year, route_date.month, route_date.day, 10, 0, tzinfo=timezone.utc)
    ends_at = starts_at + timedelta(minutes=30)
    conv_id = "conv-hash-1"
    r = await client.post(
        "/api/v1/admin/schedule/holds",
        json={
            "channel": "VOICE",
            "conversation_id": conv_id,
            "resource_id": resource_id,
            "project_id": project_id,
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
        },
    )
    _skip_if_disabled(r.status_code)
    assert r.status_code == 201, r.text
    rc = await client.post(
        "/api/v1/admin/schedule/holds/confirm",
        json={"channel": "VOICE", "conversation_id": conv_id},
    )
    assert rc.status_code == 200, rc.text

    preview = await client.post(
        "/api/v1/admin/schedule/reschedule/preview",
        json={
            "route_date": route_date.isoformat(),
            "resource_id": resource_id,
            "scope": "DAY",
            "reason": "OTHER",
            "comment": "",
            "rules": {"preserve_locked_level": 2},
        },
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()

    bad = await client.post(
        "/api/v1/admin/schedule/reschedule/confirm",
        json={
            "preview_id": body["preview_id"],
            "preview_hash": "bad" * 16,
            "reason": "OTHER",
            "comment": "",
            "expected_versions": body["expected_versions"],
        },
    )
    assert bad.status_code == 409, bad.text


@pytest.mark.asyncio
async def test_reschedule_confirm_expired_preview_409(client: AsyncClient):
    project_id = await _create_project(client)
    route_date = (_now() + timedelta(days=3)).date()
    resource_id = "00000000-0000-0000-0000-000000000022"
    _ensure_user(resource_id)

    starts_at = datetime(route_date.year, route_date.month, route_date.day, 11, 0, tzinfo=timezone.utc)
    ends_at = starts_at + timedelta(minutes=30)
    conv_id = "conv-exp-preview-1"
    r = await client.post(
        "/api/v1/admin/schedule/holds",
        json={
            "channel": "VOICE",
            "conversation_id": conv_id,
            "resource_id": resource_id,
            "project_id": project_id,
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
        },
    )
    _skip_if_disabled(r.status_code)
    assert r.status_code == 201, r.text
    rc = await client.post(
        "/api/v1/admin/schedule/holds/confirm",
        json={"channel": "VOICE", "conversation_id": conv_id},
    )
    assert rc.status_code == 200, rc.text

    preview = await client.post(
        "/api/v1/admin/schedule/reschedule/preview",
        json={
            "route_date": route_date.isoformat(),
            "resource_id": resource_id,
            "scope": "DAY",
            "reason": "WEATHER",
            "comment": "",
            "rules": {"preserve_locked_level": 2},
        },
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()

    assert SessionLocal is not None
    with SessionLocal() as db:
        prev = db.get(SchedulePreview, body["preview_id"])
        assert prev is not None
        prev.expires_at = _now() - timedelta(seconds=1)
        db.commit()

    expired = await client.post(
        "/api/v1/admin/schedule/reschedule/confirm",
        json={
            "preview_id": body["preview_id"],
            "preview_hash": body["preview_hash"],
            "reason": "WEATHER",
            "comment": "",
            "expected_versions": body["expected_versions"],
        },
    )
    assert expired.status_code == 409, expired.text


@pytest.mark.asyncio
async def test_lock_level_ge_2_requires_admin_on_confirm(
    client: AsyncClient,
    subcontractor_client: AsyncClient,
):
    project_id = await _create_project(client)
    route_date = (_now() + timedelta(days=4)).date()
    resource_id = "00000000-0000-0000-0000-000000000023"
    _ensure_user(resource_id)

    starts_at = datetime(route_date.year, route_date.month, route_date.day, 12, 0, tzinfo=timezone.utc)
    ends_at = starts_at + timedelta(minutes=30)
    conv_id = "conv-lock2-1"
    r = await client.post(
        "/api/v1/admin/schedule/holds",
        json={
            "channel": "VOICE",
            "conversation_id": conv_id,
            "resource_id": resource_id,
            "project_id": project_id,
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
        },
    )
    _skip_if_disabled(r.status_code)
    assert r.status_code == 201, r.text
    rc = await client.post(
        "/api/v1/admin/schedule/holds/confirm",
        json={"channel": "VOICE", "conversation_id": conv_id},
    )
    assert rc.status_code == 200, rc.text

    # Approve day to set lock_level=2 (ADMIN only).
    approve = await client.post(
        "/api/v1/admin/schedule/daily-approve",
        json={"route_date": route_date.isoformat(), "resource_id": resource_id, "comment": "lock day"},
    )
    assert approve.status_code == 200, approve.text

    preview = await subcontractor_client.post(
        "/api/v1/admin/schedule/reschedule/preview",
        json={
            "route_date": route_date.isoformat(),
            "resource_id": resource_id,
            "scope": "DAY",
            "reason": "OTHER",
            "comment": "",
            # Allow preview to include lock_level=2 rows so confirm can enforce ADMIN-only rule.
            "rules": {"preserve_locked_level": 3},
        },
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()

    denied = await subcontractor_client.post(
        "/api/v1/admin/schedule/reschedule/confirm",
        json={
            "preview_id": body["preview_id"],
            "preview_hash": body["preview_hash"],
            "reason": "OTHER",
            "comment": "",
            "expected_versions": body["expected_versions"],
        },
    )
    assert denied.status_code == 403, denied.text
