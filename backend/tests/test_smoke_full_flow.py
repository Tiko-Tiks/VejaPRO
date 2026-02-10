"""
Smoke test: Full DRAFT -> PAID -> SCHEDULED -> PENDING_EXPERT -> CERTIFIED -> ACTIVE flow.

Validates the complete project lifecycle works end-to-end in one test.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.core.dependencies import SessionLocal
from app.models.project import (
    ClientConfirmation,
    Evidence,
    Payment,
    Project,
    User,
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


ADMIN_ID = "00000000-0000-0000-0000-000000000001"
CONTRACTOR_ID = "00000000-0000-0000-0000-000000000070"
EXPERT_ID = "00000000-0000-0000-0000-000000000071"


def _ensure_users() -> None:
    assert SessionLocal is not None
    with SessionLocal() as db:
        for uid, role, email in [
            (ADMIN_ID, "ADMIN", "admin@test.local"),
            (CONTRACTOR_ID, "SUBCONTRACTOR", "contractor@test.local"),
            (EXPERT_ID, "EXPERT", "expert@test.local"),
        ]:
            u = db.get(User, uuid.UUID(uid))
            if not u:
                db.add(User(id=uuid.UUID(uid), email=email, role=role, is_active=True))
        db.commit()


def _create_project() -> str:
    assert SessionLocal is not None
    pid = uuid.uuid4()
    with SessionLocal() as db:
        db.add(
            Project(
                id=pid,
                client_info={"name": "Smoke Test Client", "phone": "+37061234567", "email": "smoke@test.com"},
                status="DRAFT",
            )
        )
        db.commit()
    return str(pid)


def _add_deposit_payment(project_id: str) -> None:
    assert SessionLocal is not None
    with SessionLocal() as db:
        db.add(
            Payment(
                project_id=uuid.UUID(project_id),
                provider="manual",
                amount=Decimal("50.00"),
                currency="EUR",
                payment_type="DEPOSIT",
                status="SUCCEEDED",
                payment_method="CASH",
                is_manual_confirmed=True,
                confirmed_at=_now(),
            )
        )
        db.commit()


def _add_expert_evidences(project_id: str) -> None:
    assert SessionLocal is not None
    with SessionLocal() as db:
        for i in range(3):
            db.add(
                Evidence(
                    project_id=uuid.UUID(project_id),
                    file_url=f"https://storage.test/cert_{i}.jpg",
                    category="EXPERT_CERTIFICATION",
                    uploaded_by=uuid.UUID(EXPERT_ID),
                )
            )
        db.commit()


def _add_final_payment(project_id: str) -> None:
    assert SessionLocal is not None
    with SessionLocal() as db:
        db.add(
            Payment(
                project_id=uuid.UUID(project_id),
                provider="manual",
                amount=Decimal("200.00"),
                currency="EUR",
                payment_type="FINAL",
                status="SUCCEEDED",
                payment_method="BANK_TRANSFER",
                is_manual_confirmed=True,
                confirmed_at=_now(),
            )
        )
        db.commit()


def _add_confirmed_client_confirmation(project_id: str) -> None:
    assert SessionLocal is not None
    with SessionLocal() as db:
        db.add(
            ClientConfirmation(
                project_id=uuid.UUID(project_id),
                token_hash=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
                expires_at=_now() + timedelta(hours=48),
                channel="email",
                status="CONFIRMED",
                confirmed_at=_now(),
            )
        )
        db.commit()


@pytest.mark.asyncio
async def test_full_draft_to_active_flow(client: AsyncClient):
    """Smoke test: DRAFT -> PAID -> SCHEDULED -> PENDING_EXPERT -> CERTIFIED -> ACTIVE."""
    _ensure_users()
    project_id = _create_project()

    # --- Step 1: DRAFT -> PAID ---
    _add_deposit_payment(project_id)

    r = await client.post(
        "/api/v1/transition-status",
        json={"project_id": project_id, "new_status": "PAID"},
    )
    assert r.status_code == 200, f"DRAFT->PAID failed: {r.text}"
    assert r.json()["status"] == "PAID"

    # --- Step 2: PAID -> SCHEDULED ---
    r = await client.post(
        "/api/v1/transition-status",
        json={"project_id": project_id, "new_status": "SCHEDULED"},
    )
    assert r.status_code == 200, f"PAID->SCHEDULED failed: {r.text}"
    assert r.json()["status"] == "SCHEDULED"

    # --- Step 3: SCHEDULED -> PENDING_EXPERT ---
    r = await client.post(
        "/api/v1/transition-status",
        json={"project_id": project_id, "new_status": "PENDING_EXPERT"},
    )
    assert r.status_code == 200, f"SCHEDULED->PENDING_EXPERT failed: {r.text}"
    assert r.json()["status"] == "PENDING_EXPERT"

    # --- Step 4: PENDING_EXPERT -> CERTIFIED ---
    # Uses dedicated /certify-project endpoint with checklist + evidences
    _add_expert_evidences(project_id)

    r = await client.post(
        "/api/v1/certify-project",
        json={
            "project_id": project_id,
            "checklist": {
                "pieva_nusenauta": True,
                "krastai_aptvarkyti": True,
                "smelis_pripiltas": True,
            },
            "notes": "Smoke test certification",
        },
    )
    assert r.status_code == 200, f"PENDING_EXPERT->CERTIFIED failed: {r.text}"
    assert r.json()["project_status"] == "CERTIFIED"

    # --- Step 5: CERTIFIED -> ACTIVE ---
    # Done via /public/activations/{token}/confirm (SYSTEM_EMAIL actor)
    _add_final_payment(project_id)
    _add_confirmed_client_confirmation(project_id)

    activation_token = secrets.token_urlsafe(32)
    activation_hash = hashlib.sha256(activation_token.encode("utf-8")).hexdigest()
    assert SessionLocal is not None
    with SessionLocal() as db:
        db.add(
            ClientConfirmation(
                project_id=uuid.UUID(project_id),
                token_hash=activation_hash,
                expires_at=_now() + timedelta(hours=48),
                channel="email",
                status="PENDING",
            )
        )
        db.commit()

    r = await client.post(f"/api/v1/public/activations/{activation_token}/confirm")
    assert r.status_code == 200, f"CERTIFIED->ACTIVE failed: {r.text}"
    data = r.json()
    assert data["new_status"] == "ACTIVE"
    assert data["project_id"] == project_id

    # --- Verify final state ---
    r = await client.get(f"/api/v1/projects/{project_id}")
    assert r.status_code == 200
    assert r.json()["project"]["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_invalid_transition_rejected(client: AsyncClient):
    """Verify that skipping states is rejected."""
    _ensure_users()
    project_id = _create_project()

    # Try to go directly DRAFT -> SCHEDULED (skipping PAID)
    r = await client.post(
        "/api/v1/transition-status",
        json={"project_id": project_id, "new_status": "SCHEDULED"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_draft_to_paid_without_deposit_rejected(client: AsyncClient):
    """DRAFT -> PAID without deposit payment should fail."""
    _ensure_users()
    project_id = _create_project()

    r = await client.post(
        "/api/v1/transition-status",
        json={"project_id": project_id, "new_status": "PAID"},
    )
    assert r.status_code == 400
