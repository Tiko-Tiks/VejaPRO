"""
Unit tests for transition_service — state machine, PII redaction, guards.

Covers:
  - _redact_pii: nested dict/list PII masking
  - _is_allowed_actor: RBAC per transition
  - apply_transition: happy path, disallowed transitions, actor guards, certification guards, deposit/final/confirmation guards
  - create_client_confirmation: token creation and hashing
  - find_client_confirmation: lookup by raw token
  - is_deposit_payment_recorded: real payment + waived deposit
  - is_final_payment_recorded: FINAL + SUCCEEDED requirement
  - is_client_confirmed: CONFIRMED status requirement
  - unpublish_project_evidences: marketing consent revocation
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

# ── helpers ──────────────────────────────────────────────────────────

_BASE_ENV = {
    "DATABASE_URL": "sqlite:////tmp/test_ts.db",
    "SUPABASE_URL": "https://fake.supabase.co",
    "SUPABASE_KEY": "fake-key",
    "SUPABASE_JWT_SECRET": "super-secret-jwt-key-for-testing-only-32chars",
    "SECRET_KEY": "test-secret-key",
    "ENVIRONMENT": "test",
}


def _fresh_settings(**overrides):
    import os

    env = {**_BASE_ENV, **overrides}
    with patch.dict(os.environ, env, clear=False):
        from app.core.config import Settings

        return Settings()


def _get_db():
    from app.core.dependencies import SessionLocal

    if SessionLocal is None:
        pytest.skip("DATABASE_URL is not configured")
    return SessionLocal()


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_project(db, *, status="DRAFT", client_info=None):
    from app.models.project import Project

    pid = uuid.uuid4()
    p = Project(
        id=pid,
        status=status,
        client_info=client_info or {"name": "Test", "phone": "+37060000000"},
    )
    db.add(p)
    db.flush()
    return p


def _make_payment(
    db,
    project_id,
    *,
    payment_type="DEPOSIT",
    status="SUCCEEDED",
    amount=50,
    provider="manual",
    is_manual_confirmed=True,
    payment_method="BANK_TRANSFER",
):
    from app.models.project import Payment

    pay = Payment(
        id=uuid.uuid4(),
        project_id=str(project_id),
        payment_type=payment_type,
        amount=amount,
        currency="EUR",
        status=status,
        provider=provider,
        is_manual_confirmed=is_manual_confirmed,
        payment_method=payment_method,
    )
    db.add(pay)
    db.flush()
    return pay


def _make_evidence(db, project_id, *, category="EXPERT_CERTIFICATION", show_on_web=False):
    from app.models.project import Evidence

    ev = Evidence(
        id=uuid.uuid4(),
        project_id=str(project_id),
        category=category,
        file_url=f"https://cdn.test/{uuid.uuid4()}.jpg",
        show_on_web=show_on_web,
    )
    db.add(ev)
    db.flush()
    return ev


def _make_confirmation(db, project_id, *, status="CONFIRMED"):
    from app.models.project import ClientConfirmation

    cc = ClientConfirmation(
        project_id=str(project_id),
        token_hash=hashlib.sha256(b"test-token").hexdigest(),
        expires_at=_now() + timedelta(hours=72),
        channel="email",
        status=status,
        attempts=0,
    )
    db.add(cc)
    db.flush()
    return cc


# ── PII Redaction ────────────────────────────────────────────────────


class TestRedactPII:
    def test_redacts_flat_dict(self):
        from app.services.transition_service import _redact_pii

        data = {"name": "Jonas", "phone": "+37060000000", "email": "j@test.lt"}
        result = _redact_pii(data, {"phone", "email"})
        assert result["name"] == "Jonas"
        assert result["phone"] == "[REDACTED]"
        assert result["email"] == "[REDACTED]"

    def test_redacts_nested_dict(self):
        from app.services.transition_service import _redact_pii

        data = {"client": {"phone": "+37060000000", "info": {"address": "Vilniaus g. 1"}}}
        result = _redact_pii(data, {"phone", "address"})
        assert result["client"]["phone"] == "[REDACTED]"
        assert result["client"]["info"]["address"] == "[REDACTED]"

    def test_redacts_list_of_dicts(self):
        from app.services.transition_service import _redact_pii

        data = [{"phone": "123"}, {"phone": "456"}]
        result = _redact_pii(data, {"phone"})
        assert result[0]["phone"] == "[REDACTED]"
        assert result[1]["phone"] == "[REDACTED]"

    def test_none_returns_none(self):
        from app.services.transition_service import _redact_pii

        assert _redact_pii(None, {"phone"}) is None

    def test_scalar_unchanged(self):
        from app.services.transition_service import _redact_pii

        assert _redact_pii("hello", {"phone"}) == "hello"
        assert _redact_pii(42, {"phone"}) == 42

    def test_case_insensitive_keys(self):
        from app.services.transition_service import _redact_pii

        data = {"Phone": "+37060000000", "EMAIL": "a@b.c"}
        result = _redact_pii(data, {"phone", "email"})
        assert result["Phone"] == "[REDACTED]"
        assert result["EMAIL"] == "[REDACTED]"


# ── Allowed Actor ────────────────────────────────────────────────────


class TestIsAllowedActor:
    def test_draft_to_paid_allowed(self):
        from app.schemas.project import ProjectStatus
        from app.services.transition_service import _is_allowed_actor

        assert _is_allowed_actor(ProjectStatus.DRAFT, ProjectStatus.PAID, "SYSTEM_STRIPE") is True
        assert _is_allowed_actor(ProjectStatus.DRAFT, ProjectStatus.PAID, "SUBCONTRACTOR") is True
        assert _is_allowed_actor(ProjectStatus.DRAFT, ProjectStatus.PAID, "ADMIN") is True

    def test_draft_to_paid_disallowed(self):
        from app.schemas.project import ProjectStatus
        from app.services.transition_service import _is_allowed_actor

        assert _is_allowed_actor(ProjectStatus.DRAFT, ProjectStatus.PAID, "EXPERT") is False
        assert _is_allowed_actor(ProjectStatus.DRAFT, ProjectStatus.PAID, "SYSTEM_EMAIL") is False

    def test_paid_to_scheduled(self):
        from app.schemas.project import ProjectStatus
        from app.services.transition_service import _is_allowed_actor

        assert _is_allowed_actor(ProjectStatus.PAID, ProjectStatus.SCHEDULED, "SUBCONTRACTOR") is True
        assert _is_allowed_actor(ProjectStatus.PAID, ProjectStatus.SCHEDULED, "ADMIN") is True
        assert _is_allowed_actor(ProjectStatus.PAID, ProjectStatus.SCHEDULED, "EXPERT") is False

    def test_scheduled_to_pending_expert(self):
        from app.schemas.project import ProjectStatus
        from app.services.transition_service import _is_allowed_actor

        assert _is_allowed_actor(ProjectStatus.SCHEDULED, ProjectStatus.PENDING_EXPERT, "SUBCONTRACTOR") is True
        assert _is_allowed_actor(ProjectStatus.SCHEDULED, ProjectStatus.PENDING_EXPERT, "ADMIN") is True
        assert _is_allowed_actor(ProjectStatus.SCHEDULED, ProjectStatus.PENDING_EXPERT, "SYSTEM_STRIPE") is False

    def test_pending_expert_to_certified(self):
        from app.schemas.project import ProjectStatus
        from app.services.transition_service import _is_allowed_actor

        assert _is_allowed_actor(ProjectStatus.PENDING_EXPERT, ProjectStatus.CERTIFIED, "EXPERT") is True
        assert _is_allowed_actor(ProjectStatus.PENDING_EXPERT, ProjectStatus.CERTIFIED, "ADMIN") is True
        assert _is_allowed_actor(ProjectStatus.PENDING_EXPERT, ProjectStatus.CERTIFIED, "SUBCONTRACTOR") is False

    def test_certified_to_active(self):
        from app.schemas.project import ProjectStatus
        from app.services.transition_service import _is_allowed_actor

        assert _is_allowed_actor(ProjectStatus.CERTIFIED, ProjectStatus.ACTIVE, "SYSTEM_TWILIO") is True
        assert _is_allowed_actor(ProjectStatus.CERTIFIED, ProjectStatus.ACTIVE, "SYSTEM_EMAIL") is True
        assert _is_allowed_actor(ProjectStatus.CERTIFIED, ProjectStatus.ACTIVE, "ADMIN") is False

    def test_active_to_anything_disallowed(self):
        from app.schemas.project import ProjectStatus
        from app.services.transition_service import _is_allowed_actor

        # ACTIVE is terminal
        assert _is_allowed_actor(ProjectStatus.ACTIVE, ProjectStatus.DRAFT, "ADMIN") is False


# ── Apply Transition ─────────────────────────────────────────────────


class TestApplyTransition:
    def test_idempotent_same_status(self):
        """Transition to same status returns False (no-op)."""
        from app.services.transition_service import apply_transition

        db = _get_db()
        try:
            project = _make_project(db, status="DRAFT")
            db.commit()
            from app.schemas.project import ProjectStatus

            result = apply_transition(
                db,
                project=project,
                new_status=ProjectStatus.DRAFT,
                actor_type="ADMIN",
                actor_id="admin-1",
                ip_address="127.0.0.1",
                user_agent="test",
            )
            assert result is False
        finally:
            db.close()

    def test_disallowed_transition_raises_400(self):
        """Skip from DRAFT to SCHEDULED should raise 400."""
        from fastapi import HTTPException

        from app.schemas.project import ProjectStatus
        from app.services.transition_service import apply_transition

        db = _get_db()
        try:
            project = _make_project(db, status="DRAFT")
            db.commit()

            with pytest.raises(HTTPException) as exc_info:
                apply_transition(
                    db,
                    project=project,
                    new_status=ProjectStatus.SCHEDULED,
                    actor_type="ADMIN",
                    actor_id="admin-1",
                    ip_address="127.0.0.1",
                    user_agent="test",
                )
            assert exc_info.value.status_code == 400
        finally:
            db.close()

    def test_wrong_actor_raises_403(self):
        """EXPERT cannot do DRAFT -> PAID."""
        from fastapi import HTTPException

        from app.schemas.project import ProjectStatus
        from app.services.transition_service import apply_transition

        db = _get_db()
        try:
            project = _make_project(db, status="DRAFT")
            _make_payment(db, project.id)  # deposit exists
            db.commit()

            with pytest.raises(HTTPException) as exc_info:
                apply_transition(
                    db,
                    project=project,
                    new_status=ProjectStatus.PAID,
                    actor_type="EXPERT",
                    actor_id="expert-1",
                    ip_address="127.0.0.1",
                    user_agent="test",
                )
            assert exc_info.value.status_code == 403
        finally:
            db.close()

    def test_draft_to_paid_success(self):
        """DRAFT -> PAID with deposit payment and correct actor."""
        from app.models.project import AuditLog
        from app.schemas.project import ProjectStatus
        from app.services.transition_service import apply_transition

        db = _get_db()
        try:
            project = _make_project(db, status="DRAFT")
            _make_payment(db, project.id, payment_type="DEPOSIT", amount=50)
            db.commit()

            result = apply_transition(
                db,
                project=project,
                new_status=ProjectStatus.PAID,
                actor_type="ADMIN",
                actor_id="admin-1",
                ip_address="127.0.0.1",
                user_agent="test",
            )
            db.commit()

            assert result is True
            assert project.status == "PAID"

            # Check audit log was created
            log = (
                db.query(AuditLog)
                .filter(AuditLog.entity_id == str(project.id), AuditLog.action == "STATUS_CHANGE")
                .first()
            )
            assert log is not None
            assert log.old_value == {"status": "DRAFT"}
            assert log.new_value == {"status": "PAID"}
        finally:
            db.close()

    def test_draft_to_paid_no_deposit_raises(self):
        """Cannot go DRAFT -> PAID without deposit payment."""
        from fastapi import HTTPException

        from app.schemas.project import ProjectStatus
        from app.services.transition_service import apply_transition

        db = _get_db()
        try:
            project = _make_project(db, status="DRAFT")
            db.commit()

            with pytest.raises(HTTPException) as exc_info:
                apply_transition(
                    db,
                    project=project,
                    new_status=ProjectStatus.PAID,
                    actor_type="ADMIN",
                    actor_id="admin-1",
                    ip_address="127.0.0.1",
                    user_agent="test",
                )
            assert exc_info.value.status_code == 400
            assert "Deposit" in str(exc_info.value.detail)
        finally:
            db.close()

    def test_certified_to_active_no_final_payment_raises(self):
        """Cannot go CERTIFIED -> ACTIVE without FINAL payment."""
        from fastapi import HTTPException

        from app.schemas.project import ProjectStatus
        from app.services.transition_service import apply_transition

        db = _get_db()
        try:
            project = _make_project(db, status="CERTIFIED")
            db.commit()

            with pytest.raises(HTTPException) as exc_info:
                apply_transition(
                    db,
                    project=project,
                    new_status=ProjectStatus.ACTIVE,
                    actor_type="SYSTEM_EMAIL",
                    actor_id=None,
                    ip_address=None,
                    user_agent=None,
                )
            assert exc_info.value.status_code == 400
            assert "Final payment" in str(exc_info.value.detail)
        finally:
            db.close()

    def test_certified_to_active_no_confirmation_raises(self):
        """FINAL payment exists but no client confirmation."""
        from fastapi import HTTPException

        from app.schemas.project import ProjectStatus
        from app.services.transition_service import apply_transition

        db = _get_db()
        try:
            project = _make_project(db, status="CERTIFIED")
            _make_payment(db, project.id, payment_type="FINAL", amount=200)
            db.commit()

            with pytest.raises(HTTPException) as exc_info:
                apply_transition(
                    db,
                    project=project,
                    new_status=ProjectStatus.ACTIVE,
                    actor_type="SYSTEM_EMAIL",
                    actor_id=None,
                    ip_address=None,
                    user_agent=None,
                )
            assert exc_info.value.status_code == 400
            assert "Client confirmation" in str(exc_info.value.detail)
        finally:
            db.close()

    def test_certified_to_active_success(self):
        """Full happy path: CERTIFIED -> ACTIVE with FINAL + confirmation."""
        from app.schemas.project import ProjectStatus
        from app.services.transition_service import apply_transition

        db = _get_db()
        try:
            project = _make_project(db, status="CERTIFIED")
            _make_payment(db, project.id, payment_type="FINAL", amount=200)
            _make_confirmation(db, str(project.id))
            db.commit()

            result = apply_transition(
                db,
                project=project,
                new_status=ProjectStatus.ACTIVE,
                actor_type="SYSTEM_EMAIL",
                actor_id=None,
                ip_address=None,
                user_agent=None,
            )
            db.commit()

            assert result is True
            assert project.status == "ACTIVE"
            assert project.is_certified is True
        finally:
            db.close()


# ── Certification Guards ─────────────────────────────────────────────


class TestCertificationGuards:
    def test_pending_expert_to_certified_no_checklist_raises(self):
        """Certification requires a checklist in metadata."""
        from fastapi import HTTPException

        from app.schemas.project import ProjectStatus
        from app.services.transition_service import apply_transition

        db = _get_db()
        try:
            project = _make_project(db, status="PENDING_EXPERT")
            # Need 3 evidence items
            for _ in range(3):
                _make_evidence(db, str(project.id))
            db.commit()

            with pytest.raises(HTTPException) as exc_info:
                apply_transition(
                    db,
                    project=project,
                    new_status=ProjectStatus.CERTIFIED,
                    actor_type="EXPERT",
                    actor_id="expert-1",
                    ip_address="127.0.0.1",
                    user_agent="test",
                    metadata={},  # no checklist
                )
            assert exc_info.value.status_code == 400
        finally:
            db.close()

    def test_pending_expert_to_certified_incomplete_checklist_raises(self):
        """All checklist items must be truthy."""
        from fastapi import HTTPException

        from app.schemas.project import ProjectStatus
        from app.services.transition_service import apply_transition

        db = _get_db()
        try:
            project = _make_project(db, status="PENDING_EXPERT")
            for _ in range(3):
                _make_evidence(db, str(project.id))
            db.commit()

            with pytest.raises(HTTPException) as exc_info:
                apply_transition(
                    db,
                    project=project,
                    new_status=ProjectStatus.CERTIFIED,
                    actor_type="EXPERT",
                    actor_id="expert-1",
                    ip_address="127.0.0.1",
                    user_agent="test",
                    metadata={"checklist": {"item1": True, "item2": False}},
                )
            assert exc_info.value.status_code == 400
        finally:
            db.close()

    def test_pending_expert_to_certified_insufficient_evidence_raises(self):
        """Need at least 3 EXPERT_CERTIFICATION evidences."""
        from fastapi import HTTPException

        from app.schemas.project import ProjectStatus
        from app.services.transition_service import apply_transition

        db = _get_db()
        try:
            project = _make_project(db, status="PENDING_EXPERT")
            # Only 2 evidences
            for _ in range(2):
                _make_evidence(db, str(project.id))
            db.commit()

            with pytest.raises(HTTPException) as exc_info:
                apply_transition(
                    db,
                    project=project,
                    new_status=ProjectStatus.CERTIFIED,
                    actor_type="EXPERT",
                    actor_id="expert-1",
                    ip_address="127.0.0.1",
                    user_agent="test",
                    metadata={"checklist": {"item1": True, "item2": True}},
                )
            assert exc_info.value.status_code == 400
            assert "3" in str(exc_info.value.detail)
        finally:
            db.close()

    def test_pending_expert_to_certified_success(self):
        """Full happy path for certification."""
        from app.schemas.project import ProjectStatus
        from app.services.transition_service import apply_transition

        db = _get_db()
        try:
            project = _make_project(db, status="PENDING_EXPERT")
            for _ in range(3):
                _make_evidence(db, str(project.id))
            db.commit()

            result = apply_transition(
                db,
                project=project,
                new_status=ProjectStatus.CERTIFIED,
                actor_type="EXPERT",
                actor_id="expert-1",
                ip_address="127.0.0.1",
                user_agent="test",
                metadata={"checklist": {"foundation": True, "walls": True, "roof": True}},
            )
            db.commit()

            assert result is True
            assert project.status == "CERTIFIED"
            assert project.is_certified is True
        finally:
            db.close()


# ── Deposit/Payment Guards ───────────────────────────────────────────


class TestPaymentGuards:
    def test_deposit_payment_real(self):
        """Real deposit (amount > 0) satisfies the guard."""
        from app.services.transition_service import is_deposit_payment_recorded

        db = _get_db()
        try:
            project = _make_project(db)
            _make_payment(db, project.id, payment_type="DEPOSIT", amount=50, provider="manual")
            db.commit()

            assert is_deposit_payment_recorded(db, str(project.id)) is True
        finally:
            db.close()

    def test_deposit_waived(self):
        """Waived deposit (amount=0, WAIVED method) satisfies the guard."""
        from app.services.transition_service import is_deposit_payment_recorded

        db = _get_db()
        try:
            project = _make_project(db)
            _make_payment(
                db,
                project.id,
                payment_type="DEPOSIT",
                amount=0,
                provider="manual",
                is_manual_confirmed=True,
                payment_method="WAIVED",
            )
            db.commit()

            assert is_deposit_payment_recorded(db, str(project.id)) is True
        finally:
            db.close()

    def test_deposit_not_recorded(self):
        """No deposit payment -> guard fails."""
        from app.services.transition_service import is_deposit_payment_recorded

        db = _get_db()
        try:
            project = _make_project(db)
            db.commit()

            assert is_deposit_payment_recorded(db, str(project.id)) is False
        finally:
            db.close()

    def test_deposit_pending_not_counted(self):
        """PENDING deposit does not satisfy the guard."""
        from app.services.transition_service import is_deposit_payment_recorded

        db = _get_db()
        try:
            project = _make_project(db)
            _make_payment(db, project.id, payment_type="DEPOSIT", amount=50, status="PENDING")
            db.commit()

            assert is_deposit_payment_recorded(db, str(project.id)) is False
        finally:
            db.close()

    def test_final_payment_recorded(self):
        from app.services.transition_service import is_final_payment_recorded

        db = _get_db()
        try:
            project = _make_project(db)
            _make_payment(db, project.id, payment_type="FINAL", amount=200)
            db.commit()

            assert is_final_payment_recorded(db, str(project.id)) is True
        finally:
            db.close()

    def test_final_payment_not_recorded(self):
        from app.services.transition_service import is_final_payment_recorded

        db = _get_db()
        try:
            project = _make_project(db)
            db.commit()

            assert is_final_payment_recorded(db, str(project.id)) is False
        finally:
            db.close()


# ── Client Confirmation ──────────────────────────────────────────────


class TestClientConfirmation:
    def test_create_returns_raw_token(self):
        from app.services.transition_service import create_client_confirmation

        db = _get_db()
        try:
            project = _make_project(db)
            db.commit()

            token = create_client_confirmation(db, str(project.id), ttl_hours=48, channel="email")
            db.commit()

            assert isinstance(token, str)
            assert len(token) > 0
        finally:
            db.close()

    def test_find_by_token(self):
        from app.services.transition_service import create_client_confirmation, find_client_confirmation

        db = _get_db()
        try:
            project = _make_project(db)
            db.commit()

            token = create_client_confirmation(db, str(project.id), channel="email")
            db.commit()

            found = find_client_confirmation(db, token)
            assert found is not None
            assert str(found.project_id) == str(project.id)
            assert found.status == "PENDING"
            assert found.channel == "email"
        finally:
            db.close()

    def test_find_wrong_token_returns_none(self):
        from app.services.transition_service import find_client_confirmation

        db = _get_db()
        try:
            found = find_client_confirmation(db, "WRONG-TOKEN-XYZ")
            assert found is None
        finally:
            db.close()

    def test_is_client_confirmed_true(self):
        from app.services.transition_service import is_client_confirmed

        db = _get_db()
        try:
            project = _make_project(db)
            _make_confirmation(db, str(project.id), status="CONFIRMED")
            db.commit()

            assert is_client_confirmed(db, str(project.id)) is True
        finally:
            db.close()

    def test_is_client_confirmed_pending_false(self):
        from app.services.transition_service import is_client_confirmed

        db = _get_db()
        try:
            project = _make_project(db)
            _make_confirmation(db, str(project.id), status="PENDING")
            db.commit()

            assert is_client_confirmed(db, str(project.id)) is False
        finally:
            db.close()

    def test_increment_attempt(self):
        from app.services.transition_service import increment_confirmation_attempt

        db = _get_db()
        try:
            project = _make_project(db)
            cc = _make_confirmation(db, str(project.id))
            db.commit()

            assert cc.attempts == 0
            increment_confirmation_attempt(db, cc)
            assert cc.attempts == 1
            increment_confirmation_attempt(db, cc)
            assert cc.attempts == 2
        finally:
            db.close()


# ── Unpublish Evidences ──────────────────────────────────────────────


class TestUnpublishEvidences:
    def test_unpublish_web_evidences(self):
        from app.services.transition_service import unpublish_project_evidences

        db = _get_db()
        try:
            project = _make_project(db)
            _make_evidence(db, str(project.id), show_on_web=True)
            _make_evidence(db, str(project.id), show_on_web=True)
            _make_evidence(db, str(project.id), show_on_web=False)  # already hidden
            db.commit()

            count = unpublish_project_evidences(
                db,
                str(project.id),
                actor_type="ADMIN",
                actor_id="admin-1",
                ip_address="127.0.0.1",
                user_agent="test",
            )
            db.commit()

            assert count == 2

            # Verify all show_on_web are now False
            from app.models.project import Evidence

            evs = db.query(Evidence).filter(Evidence.project_id == str(project.id)).all()
            assert all(ev.show_on_web is False for ev in evs)
        finally:
            db.close()

    def test_unpublish_no_web_evidences(self):
        from app.services.transition_service import unpublish_project_evidences

        db = _get_db()
        try:
            project = _make_project(db)
            _make_evidence(db, str(project.id), show_on_web=False)
            db.commit()

            count = unpublish_project_evidences(
                db,
                str(project.id),
                actor_type="ADMIN",
                actor_id="admin-1",
                ip_address="127.0.0.1",
                user_agent="test",
            )
            assert count == 0
        finally:
            db.close()
