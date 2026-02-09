"""V2.2 Email Intake tests — admin questionnaire, offer lifecycle,
public accept/reject, activation confirm, max attempts."""

import hashlib
import os
import secrets
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import CurrentUser, get_current_user
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.main import app
from app.models.project import (
    Appointment,
    AuditLog,
    Base,
    CallRequest,
    ClientConfirmation,
    Project,
    User,
)


def _now_naive():
    """Naive UTC now for SQLite compat."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _tomorrow_9am():
    now = _now_naive()
    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)


# ─── Admin endpoints ──────────────────────────────────


class IntakeAdminEndpointTests(unittest.TestCase):
    """Admin intake state, questionnaire, prepare-offer, send-offer."""

    def setUp(self):
        get_settings.cache_clear()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        self.admin_user = CurrentUser(id=str(uuid.uuid4()), role="ADMIN")

        def override_get_current_user():
            return self.admin_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        get_settings.cache_clear()

    # helpers

    def _create_call_request(self, intake_state=None, **kwargs):
        db = self.SessionLocal()
        cr = CallRequest(
            name=kwargs.get("name", "Test Client"),
            phone=kwargs.get("phone", "+37060000001"),
            email=kwargs.get("email", "client@test.lt"),
            status=kwargs.get("status", "NEW"),
            intake_state=intake_state or {},
        )
        db.add(cr)
        db.commit()
        db.refresh(cr)
        db.close()
        return cr

    def _create_user(self, role="ADMIN"):
        db = self.SessionLocal()
        user = User(
            email=f"{uuid.uuid4()}@example.com",
            role=role,
            created_at=_now_naive(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.close()
        return user

    def _complete_questionnaire_state(self):
        return {
            "questionnaire": {
                "email": {"value": "client@test.lt", "source": "operator", "confidence": 1.0},
                "address": {"value": "Vilniaus g. 1, Vilnius", "source": "operator", "confidence": 1.0},
                "service_type": {"value": "LAWN_CARE", "source": "operator", "confidence": 1.0},
            },
            "workflow": {"row_version": 1, "phase": "QUESTIONNAIRE_DONE"},
        }

    # ── Feature flag ───────────────────

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "false"}, clear=False)
    def test_feature_flag_disabled_returns_404(self):
        cr = self._create_call_request()
        resp = self.client.get(f"/api/v1/admin/intake/{cr.id}/state")
        self.assertEqual(resp.status_code, 404)

    # ── GET state ──────────────────────

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_get_intake_state_success(self):
        cr = self._create_call_request(intake_state=self._complete_questionnaire_state())
        resp = self.client.get(f"/api/v1/admin/intake/{cr.id}/state")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["call_request_id"], str(cr.id))
        self.assertTrue(data["questionnaire_complete"])

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_get_intake_state_empty_questionnaire(self):
        cr = self._create_call_request()
        resp = self.client.get(f"/api/v1/admin/intake/{cr.id}/state")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["questionnaire_complete"])

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_get_intake_state_nonexistent_404(self):
        resp = self.client.get(f"/api/v1/admin/intake/{uuid.uuid4()}/state")
        self.assertEqual(resp.status_code, 404)

    # ── RBAC ───────────────────────────

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_rbac_non_admin_rejected(self):
        self.admin_user = CurrentUser(id=str(uuid.uuid4()), role="SUBCONTRACTOR")

        def override():
            return self.admin_user

        app.dependency_overrides[get_current_user] = override
        cr = self._create_call_request()
        resp = self.client.get(f"/api/v1/admin/intake/{cr.id}/state")
        self.assertEqual(resp.status_code, 403)

    # ── PATCH questionnaire ────────────

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_update_questionnaire_partial_patch(self):
        cr = self._create_call_request()
        resp = self.client.patch(
            f"/api/v1/admin/intake/{cr.id}/questionnaire",
            json={"email": "new@test.lt"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        q = data["questionnaire"]
        self.assertIn("email", q)

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_optimistic_lock_conflict_409(self):
        state = self._complete_questionnaire_state()
        state["workflow"]["row_version"] = 5
        cr = self._create_call_request(intake_state=state)
        resp = self.client.patch(
            f"/api/v1/admin/intake/{cr.id}/questionnaire",
            json={"email": "new@test.lt", "expected_row_version": 1},
        )
        self.assertEqual(resp.status_code, 409)

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_optimistic_lock_success(self):
        state = {"questionnaire": {}, "workflow": {"row_version": 3}}
        cr = self._create_call_request(intake_state=state)
        resp = self.client.patch(
            f"/api/v1/admin/intake/{cr.id}/questionnaire",
            json={"email": "new@test.lt", "expected_row_version": 3},
        )
        self.assertEqual(resp.status_code, 200)

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_autoprepare_on_complete_questionnaire(self):
        """Completing the last required field triggers auto-prepare."""
        self._create_user()  # resource for slot resolution
        state = {
            "questionnaire": {
                "email": {"value": "client@test.lt", "source": "operator", "confidence": 1.0},
                "address": {"value": "Vilniaus g. 1", "source": "operator", "confidence": 1.0},
            },
            "workflow": {"row_version": 1},
        }
        cr = self._create_call_request(intake_state=state)
        resp = self.client.patch(
            f"/api/v1/admin/intake/{cr.id}/questionnaire",
            json={"service_type": "LAWN_CARE"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["questionnaire_complete"])
        # Auto-prepare should have found a slot
        ao = data.get("active_offer") or {}
        self.assertIn("slot", ao)

    # ── POST prepare-offer ─────────────

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_prepare_offer_incomplete_400(self):
        cr = self._create_call_request()  # empty questionnaire
        resp = self.client.post(
            f"/api/v1/admin/intake/{cr.id}/prepare-offer",
            json={"kind": "INSPECTION"},
        )
        self.assertEqual(resp.status_code, 400)

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_prepare_offer_success(self):
        self._create_user()
        cr = self._create_call_request(intake_state=self._complete_questionnaire_state())
        resp = self.client.post(
            f"/api/v1/admin/intake/{cr.id}/prepare-offer",
            json={"kind": "INSPECTION"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNotNone(data["slot_start"])
        self.assertIsNotNone(data["slot_end"])
        self.assertEqual(data["phase"], "OFFER_PREPARED")

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_prepare_offer_row_version_409(self):
        self._create_user()
        state = self._complete_questionnaire_state()
        state["workflow"]["row_version"] = 5
        cr = self._create_call_request(intake_state=state)
        resp = self.client.post(
            f"/api/v1/admin/intake/{cr.id}/prepare-offer",
            json={"kind": "INSPECTION", "expected_row_version": 1},
        )
        self.assertEqual(resp.status_code, 409)

    # ── POST send-offer ────────────────

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_send_offer_creates_appointment_201(self):
        self._create_user()
        cr = self._create_call_request(intake_state=self._complete_questionnaire_state())
        resp = self.client.post(f"/api/v1/admin/intake/{cr.id}/send-offer")
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data["appointment_id"])
        self.assertTrue(data["hold_expires_at"])
        self.assertEqual(data["attempt_no"], 1)
        self.assertEqual(data["phase"], "OFFER_SENT")

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_send_offer_audit_log_created(self):
        self._create_user()
        cr = self._create_call_request(intake_state=self._complete_questionnaire_state())
        self.client.post(f"/api/v1/admin/intake/{cr.id}/send-offer")

        db = self.SessionLocal()
        logs = db.query(AuditLog).filter(AuditLog.action == "OFFER_SENT").all()
        db.close()
        self.assertGreaterEqual(len(logs), 1)
        self.assertEqual(str(logs[0].entity_id), str(cr.id))

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_send_offer_incomplete_400(self):
        cr = self._create_call_request()
        resp = self.client.post(f"/api/v1/admin/intake/{cr.id}/send-offer")
        self.assertEqual(resp.status_code, 400)


# ─── Public endpoints ──────────────────────────────────


class IntakePublicEndpointTests(unittest.TestCase):
    """Public offer view, accept, reject endpoints."""

    def setUp(self):
        get_settings.cache_clear()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        # Admin auth needed for setup calls only
        self.admin_user = CurrentUser(id=str(uuid.uuid4()), role="ADMIN")

        def override_get_current_user():
            return self.admin_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        get_settings.cache_clear()

    def _create_user(self, role="ADMIN"):
        db = self.SessionLocal()
        user = User(
            email=f"{uuid.uuid4()}@example.com",
            role=role,
            created_at=_now_naive(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.close()
        return user

    def _create_call_request_with_sent_offer(self):
        """Create a CR that has gone through the full send-offer lifecycle."""
        user = self._create_user()
        db = self.SessionLocal()

        public_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(public_token.encode("utf-8")).hexdigest()

        now = _now_naive()
        tomorrow_9 = _tomorrow_9am()

        cr = CallRequest(
            name="Test Client",
            phone="+37060000001",
            email="client@test.lt",
            intake_state={
                "questionnaire": {
                    "email": {"value": "client@test.lt", "source": "operator", "confidence": 1.0},
                    "address": {"value": "Vilniaus g. 1", "source": "operator", "confidence": 1.0},
                    "service_type": {"value": "LAWN_CARE", "source": "operator", "confidence": 1.0},
                },
                "workflow": {"row_version": 3, "phase": "OFFER_SENT"},
                "active_offer": {
                    "state": "SENT",
                    "kind": "INSPECTION",
                    "slot": {
                        "start": tomorrow_9.isoformat(),
                        "end": (tomorrow_9 + timedelta(hours=1)).isoformat(),
                        "resource_id": str(user.id),
                    },
                    "appointment_id": None,
                    "hold_expires_at": (now + timedelta(minutes=30)).isoformat(),
                    "token_hash": token_hash,
                    "channel": "email",
                    "attempt_no": 1,
                },
                "offer_history": [],
            },
        )
        db.add(cr)
        db.flush()

        appt = Appointment(
            call_request_id=cr.id,
            resource_id=user.id,
            visit_type="PRIMARY",
            starts_at=tomorrow_9,
            ends_at=tomorrow_9 + timedelta(hours=1),
            status="HELD",
            hold_expires_at=now + timedelta(minutes=30),
            lock_level=0,
            row_version=1,
            route_date=tomorrow_9.date(),
        )
        db.add(appt)
        db.flush()

        # Link appointment_id in intake_state
        state = cr.intake_state
        state["active_offer"]["appointment_id"] = str(appt.id)
        cr.intake_state = state
        db.add(cr)
        db.commit()
        db.refresh(cr)
        db.close()

        return cr, public_token, user

    # ── GET public offer ───────────────

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_public_offer_view_valid_token(self):
        cr, token, _ = self._create_call_request_with_sent_offer()
        resp = self.client.get(f"/api/v1/public/offer/{token}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["kind"], "INSPECTION")
        self.assertEqual(data["status"], "SENT")
        self.assertIsNotNone(data["slot_start"])

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_public_offer_view_invalid_token_404(self):
        resp = self.client.get(f"/api/v1/public/offer/{secrets.token_urlsafe(32)}")
        self.assertEqual(resp.status_code, 404)

    # ── POST respond accept ────────────

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_respond_accept(self):
        cr, token, _ = self._create_call_request_with_sent_offer()
        resp = self.client.post(
            f"/api/v1/public/offer/{token}/respond",
            json={"action": "accept"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ACCEPTED")

        # Verify appointment was confirmed
        db = self.SessionLocal()
        state = db.get(CallRequest, cr.id).intake_state
        appt_id = state["active_offer"]["appointment_id"]
        appt = db.get(Appointment, appt_id)
        self.assertEqual(appt.status, "CONFIRMED")
        db.close()

    # ── POST respond reject ────────────

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_respond_reject_prepares_next(self):
        self._create_user()  # extra user for slot resolution
        cr, token, _ = self._create_call_request_with_sent_offer()
        resp = self.client.post(
            f"/api/v1/public/offer/{token}/respond",
            json={"action": "reject", "suggest_text": "Not available then"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "REJECTED")

    # ── Invalid token / action ─────────

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_respond_invalid_token_404(self):
        resp = self.client.post(
            f"/api/v1/public/offer/{secrets.token_urlsafe(32)}/respond",
            json={"action": "accept"},
        )
        self.assertEqual(resp.status_code, 404)

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_respond_invalid_action_422(self):
        cr, token, _ = self._create_call_request_with_sent_offer()
        resp = self.client.post(
            f"/api/v1/public/offer/{token}/respond",
            json={"action": "maybe"},
        )
        self.assertEqual(resp.status_code, 422)

    # ── Audit logs ─────────────────────

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_accept_audit_log(self):
        cr, token, _ = self._create_call_request_with_sent_offer()
        self.client.post(f"/api/v1/public/offer/{token}/respond", json={"action": "accept"})

        db = self.SessionLocal()
        logs = db.query(AuditLog).filter(AuditLog.action == "OFFER_ACCEPTED").all()
        db.close()
        self.assertGreaterEqual(len(logs), 1)

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_reject_audit_log(self):
        self._create_user()
        cr, token, _ = self._create_call_request_with_sent_offer()
        self.client.post(f"/api/v1/public/offer/{token}/respond", json={"action": "reject"})

        db = self.SessionLocal()
        logs = db.query(AuditLog).filter(AuditLog.action == "OFFER_REJECTED").all()
        db.close()
        self.assertGreaterEqual(len(logs), 1)


# ─── Activation confirm ──────────────────────────────


class IntakeActivationTests(unittest.TestCase):
    """POST /public/activations/{token}/confirm — CERTIFIED→ACTIVE."""

    def setUp(self):
        get_settings.cache_clear()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        get_settings.cache_clear()

    def _create_certified_project_with_confirmation(self, expired=False):
        db = self.SessionLocal()
        project = Project(
            client_info={"client_id": "c-1", "email": "client@test.lt"},
            status="CERTIFIED",
        )
        db.add(project)
        db.flush()

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        if expired:
            expires_at = _now_naive() - timedelta(hours=1)
        else:
            expires_at = _now_naive() + timedelta(hours=72)

        confirmation = ClientConfirmation(
            project_id=project.id,
            token_hash=token_hash,
            expires_at=expires_at,
            channel="email",
            status="PENDING",
        )
        db.add(confirmation)
        db.commit()
        db.refresh(project)
        db.close()
        return project, token

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_activation_certified_to_active(self):
        project, token = self._create_certified_project_with_confirmation()
        resp = self.client.post(f"/api/v1/public/activations/{token}/confirm")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["new_status"], "ACTIVE")
        self.assertEqual(data["project_id"], str(project.id))

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_activation_invalid_token_404(self):
        resp = self.client.post(f"/api/v1/public/activations/{secrets.token_urlsafe(32)}/confirm")
        self.assertEqual(resp.status_code, 404)

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_activation_already_used_400(self):
        project, token = self._create_certified_project_with_confirmation()
        resp1 = self.client.post(f"/api/v1/public/activations/{token}/confirm")
        self.assertEqual(resp1.status_code, 200)

        resp2 = self.client.post(f"/api/v1/public/activations/{token}/confirm")
        self.assertEqual(resp2.status_code, 400)

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_activation_expired_400(self):
        _, token = self._create_certified_project_with_confirmation(expired=True)
        resp = self.client.post(f"/api/v1/public/activations/{token}/confirm")
        self.assertEqual(resp.status_code, 400)

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_activation_wrong_status_400(self):
        """Project not in CERTIFIED status should fail."""
        db = self.SessionLocal()
        project = Project(
            client_info={"client_id": "c-1", "email": "client@test.lt"},
            status="PAID",
        )
        db.add(project)
        db.flush()

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        confirmation = ClientConfirmation(
            project_id=project.id,
            token_hash=token_hash,
            expires_at=_now_naive() + timedelta(hours=72),
            channel="email",
            status="PENDING",
        )
        db.add(confirmation)
        db.commit()
        db.close()

        resp = self.client.post(f"/api/v1/public/activations/{token}/confirm")
        self.assertEqual(resp.status_code, 400)


# ─── Max attempts ─────────────────────────────────────


class IntakeMaxAttemptsTests(unittest.TestCase):
    """Guard against exceeding max offer attempts."""

    def setUp(self):
        get_settings.cache_clear()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        self.admin_user = CurrentUser(id=str(uuid.uuid4()), role="ADMIN")

        def override_get_current_user():
            return self.admin_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        get_settings.cache_clear()

    def _create_user(self):
        db = self.SessionLocal()
        user = User(
            email=f"{uuid.uuid4()}@example.com",
            role="ADMIN",
            created_at=_now_naive(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.close()
        return user

    @patch.dict(
        os.environ,
        {"ENABLE_EMAIL_INTAKE": "true", "EMAIL_OFFER_MAX_ATTEMPTS": "1"},
        clear=False,
    )
    def test_max_attempts_blocks_send(self):
        self._create_user()
        db = self.SessionLocal()
        cr = CallRequest(
            name="Test",
            phone="+37060000001",
            email="client@test.lt",
            intake_state={
                "questionnaire": {
                    "email": {"value": "client@test.lt", "source": "operator", "confidence": 1.0},
                    "address": {"value": "Addr 1", "source": "operator", "confidence": 1.0},
                    "service_type": {"value": "LAWN_CARE", "source": "operator", "confidence": 1.0},
                },
                "workflow": {"row_version": 1, "phase": "OFFER_PREPARED"},
                "active_offer": {
                    "state": "PREPARED",
                    "kind": "INSPECTION",
                    "slot": {
                        "start": _tomorrow_9am().isoformat(),
                        "end": (_tomorrow_9am() + timedelta(hours=1)).isoformat(),
                        "resource_id": str(uuid.uuid4()),
                    },
                    "attempt_no": 1,
                },
                "offer_history": [],
            },
        )
        db.add(cr)
        db.commit()
        db.refresh(cr)
        db.close()

        resp = self.client.post(f"/api/v1/admin/intake/{cr.id}/send-offer")
        self.assertEqual(resp.status_code, 400)

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_attempt_increments(self):
        self._create_user()
        db = self.SessionLocal()
        cr = CallRequest(
            name="Test",
            phone="+37060000001",
            email="client@test.lt",
            intake_state={
                "questionnaire": {
                    "email": {"value": "client@test.lt", "source": "operator", "confidence": 1.0},
                    "address": {"value": "Addr 1", "source": "operator", "confidence": 1.0},
                    "service_type": {"value": "LAWN_CARE", "source": "operator", "confidence": 1.0},
                },
                "workflow": {"row_version": 1, "phase": "QUESTIONNAIRE_DONE"},
            },
        )
        db.add(cr)
        db.commit()
        db.refresh(cr)
        db.close()

        resp = self.client.post(f"/api/v1/admin/intake/{cr.id}/send-offer")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["attempt_no"], 1)


if __name__ == "__main__":
    unittest.main()
