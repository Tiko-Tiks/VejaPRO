"""
Smoke test: Full DRAFT -> PAID -> SCHEDULED -> PENDING_EXPERT -> CERTIFIED -> ACTIVE flow.

Validates the complete project lifecycle works end-to-end in one test.
Tests: DB-helper flow, API-first flow, email intake E2E.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.dependencies import SessionLocal
from app.models.project import (
    CallRequest,
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


# ---------------------------------------------------------------------------
# API-first E2E: DRAFT -> ACTIVE using real API endpoints (not DB helpers)
# ---------------------------------------------------------------------------

_FINANCE_FLAGS = {
    "ENABLE_FINANCE_LEDGER": "true",
    "ENABLE_MANUAL_PAYMENTS": "true",
}


@pytest.mark.asyncio
@patch.dict(os.environ, _FINANCE_FLAGS, clear=False)
async def test_full_flow_via_api_endpoints(client: AsyncClient):
    """E2E via API endpoints: create project, quick-payment, upload evidence, certify, activate."""
    get_settings.cache_clear()
    _ensure_users()

    # --- Step 1: Create project via API ---
    r = await client.post(
        "/api/v1/projects",
        json={
            "client_info": {
                "name": "API E2E Client",
                "phone": "+37069999999",
                "email": "apie2e@test.com",
            },
            "area_m2": 120.0,
        },
    )
    assert r.status_code == 201, f"Create project failed: {r.text}"
    project_id = r.json()["id"]

    # --- Step 2: Record deposit + auto-transition to PAID ---
    r = await client.post(
        f"/api/v1/projects/{project_id}/quick-payment-and-transition",
        json={
            "payment_type": "DEPOSIT",
            "amount": 50.0,
            "currency": "EUR",
            "payment_method": "CASH",
            "provider_event_id": str(uuid.uuid4()),
            "notes": "E2E deposit",
            "transition_to": "PAID",
        },
    )
    assert r.status_code == 200, f"Deposit+PAID failed: {r.text}"
    data = r.json()
    assert data["success"] is True
    assert data["status_changed"] is True
    assert data["new_status"] == "PAID"

    # --- Step 3: PAID -> SCHEDULED ---
    r = await client.post(
        "/api/v1/transition-status",
        json={"project_id": project_id, "new_status": "SCHEDULED"},
    )
    assert r.status_code == 200, f"PAID->SCHEDULED failed: {r.text}"

    # --- Step 4: SCHEDULED -> PENDING_EXPERT ---
    r = await client.post(
        "/api/v1/transition-status",
        json={"project_id": project_id, "new_status": "PENDING_EXPERT"},
    )
    assert r.status_code == 200, f"SCHEDULED->PENDING_EXPERT failed: {r.text}"

    # --- Step 5: Upload 3 expert evidences via API ---
    # upload-evidence requires EXPERT role, but ADMIN is also allowed for certify.
    # Use DB helper for evidences (upload-evidence needs SUBCONTRACTOR/EXPERT role).
    _add_expert_evidences(project_id)

    # --- Step 6: Certify via API ---
    r = await client.post(
        "/api/v1/certify-project",
        json={
            "project_id": project_id,
            "checklist": {
                "pieva_nusenauta": True,
                "krastai_aptvarkyti": True,
                "smelis_pripiltas": True,
            },
            "notes": "API E2E certification",
        },
    )
    assert r.status_code == 200, f"Certify failed: {r.text}"
    assert r.json()["project_status"] == "CERTIFIED"

    # --- Step 7: Record final payment via API ---
    r = await client.post(
        f"/api/v1/projects/{project_id}/quick-payment-and-transition",
        json={
            "payment_type": "FINAL",
            "amount": 200.0,
            "currency": "EUR",
            "payment_method": "BANK_TRANSFER",
            "provider_event_id": str(uuid.uuid4()),
            "notes": "E2E final",
        },
    )
    assert r.status_code == 200, f"Final payment failed: {r.text}"
    assert r.json()["success"] is True

    # --- Step 8: Activate via public confirmation token ---
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
    assert r.status_code == 200, f"Activation failed: {r.text}"
    assert r.json()["new_status"] == "ACTIVE"

    # --- Verify final state ---
    r = await client.get(f"/api/v1/projects/{project_id}")
    assert r.status_code == 200
    assert r.json()["project"]["status"] == "ACTIVE"


# ---------------------------------------------------------------------------
# Email Intake E2E: call request -> questionnaire -> offer -> accept
# ---------------------------------------------------------------------------

_INTAKE_FLAGS = {
    "ENABLE_EMAIL_INTAKE": "true",
    "ENABLE_SCHEDULE_ENGINE": "true",
    "ENABLE_CALENDAR": "true",
}


def _create_call_request() -> str:
    """Insert a CallRequest directly (simulates incoming call/chat/public form)."""
    assert SessionLocal is not None
    cr_id = uuid.uuid4()
    with SessionLocal() as db:
        db.add(
            CallRequest(
                id=cr_id,
                name="Intake E2E Client",
                phone="+37061111111",
                email="intake-e2e@test.com",
                status="NEW",
                source="public",
                preferred_channel="email",
                intake_state={},
            )
        )
        db.commit()
    return str(cr_id)


@pytest.mark.asyncio
@patch.dict(os.environ, _INTAKE_FLAGS, clear=False)
async def test_email_intake_full_flow(client: AsyncClient):
    """E2E: call request -> questionnaire -> prepare offer -> send -> public accept."""
    get_settings.cache_clear()
    _ensure_users()
    cr_id = _create_call_request()

    # --- Step 1: Get intake state (should be empty/QUESTIONNAIRE phase) ---
    r = await client.get(f"/api/v1/admin/intake/{cr_id}/state")
    assert r.status_code == 200, f"Get intake state failed: {r.text}"

    # --- Step 2: Fill questionnaire (required: email, address, service_type) ---
    r = await client.patch(
        f"/api/v1/admin/intake/{cr_id}/questionnaire",
        json={
            "email": "intake-e2e@test.com",
            "address": "Vilniaus g. 10, Vilnius",
            "service_type": "Vejos irengimas",
            "phone": "+37061111111",
            "notes": "E2E test intake",
        },
    )
    assert r.status_code == 200, f"Questionnaire update failed: {r.text}"

    # --- Step 3: Prepare offer ---
    r = await client.post(
        f"/api/v1/admin/intake/{cr_id}/prepare-offer",
        json={"kind": "INSPECTION"},
    )
    assert r.status_code == 200, f"Prepare offer failed: {r.text}"

    # --- Step 4: Send offer (enqueues email) ---
    r = await client.post(f"/api/v1/admin/intake/{cr_id}/send-offer")
    assert r.status_code == 201, f"Send offer failed: {r.text}"

    # --- Step 5: Extract offer token from DB ---
    assert SessionLocal is not None
    with SessionLocal() as db:
        cr = db.get(CallRequest, uuid.UUID(cr_id))
        assert cr is not None
        state = cr.intake_state or {}
        offer_token_hash = state.get("active_offer", {}).get("token_hash")
        assert offer_token_hash, f"No offer token hash in state: {state}"
        # We need the raw token — find it from the notification outbox or client_confirmations.
        # Since send_offer creates a raw token and hashes it, we can't reverse it.
        # Instead, create a known token and inject it.

    # Create a known token that matches the hash
    known_token = secrets.token_urlsafe(32)
    known_hash = hashlib.sha256(known_token.encode("utf-8")).hexdigest()

    with SessionLocal() as db:
        cr = db.get(CallRequest, uuid.UUID(cr_id))
        assert cr is not None
        state = dict(cr.intake_state) if cr.intake_state else {}
        if "active_offer" in state:
            state["active_offer"]["token_hash"] = known_hash
            cr.intake_state = state
            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(cr, "intake_state")
            db.commit()

    # --- Step 6: View offer (public) ---
    r = await client.get(f"/api/v1/public/offer/{known_token}")
    assert r.status_code == 200, f"View offer failed: {r.text}"

    # --- Step 7: Accept offer (public) ---
    r = await client.post(
        f"/api/v1/public/offer/{known_token}/respond",
        json={"action": "accept"},
    )
    assert r.status_code == 200, f"Accept offer failed: {r.text}"

    # --- Verify: intake phase should be INSPECTION_SCHEDULED ---
    r = await client.get(f"/api/v1/admin/intake/{cr_id}/state")
    assert r.status_code == 200
    data = r.json()
    phase = data.get("workflow", {}).get("phase", "")
    assert phase == "INSPECTION_SCHEDULED", f"Expected INSPECTION_SCHEDULED, got: {phase}"
