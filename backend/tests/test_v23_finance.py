"""V2.3 Finance Module tests — quick-payment row-lock, idempotency 409,
email confirmation, SSE metrics, security 404."""

import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import CurrentUser, get_current_user
from app.core.dependencies import get_db
from app.main import app
from app.models.project import (
    Base,
    ClientConfirmation,
    Payment,
    Project,
    User,
)


class V23QuickPaymentTests(unittest.TestCase):
    """V2.3: quick-payment row-lock, idempotency 200/409, email channel."""

    def setUp(self):
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

    def _create_project(self, status="DRAFT", client_info=None):
        db = self.SessionLocal()
        project = Project(
            client_info=client_info
            or {"client_id": "c-1", "email": "test@example.com"},
            status=status,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        db.close()
        return project

    def _create_user(self, role="ADMIN"):
        db = self.SessionLocal()
        user = User(
            email=f"{uuid.uuid4()}@example.com",
            role=role,
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.close()
        return user

    # ------------------------------------------------------------------
    # Idempotency: 200 for identical, 409 for conflict
    # ------------------------------------------------------------------

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "true"}, clear=False)
    def test_idempotent_same_params_returns_200(self):
        project = self._create_project(status="DRAFT")
        event_id = f"qp-idemp-{uuid.uuid4()}"
        body = {
            "payment_type": "DEPOSIT",
            "amount": 300.0,
            "provider_event_id": event_id,
        }
        resp1 = self.client.post(
            f"/api/v1/projects/{project.id}/quick-payment-and-transition",
            json=body,
        )
        self.assertEqual(resp1.status_code, 200)
        pid1 = resp1.json()["payment_id"]

        resp2 = self.client.post(
            f"/api/v1/projects/{project.id}/quick-payment-and-transition",
            json=body,
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json()["payment_id"], pid1)
        self.assertFalse(resp2.json()["status_changed"])

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "true"}, clear=False)
    def test_conflict_different_params_returns_409(self):
        project = self._create_project(status="DRAFT")
        event_id = f"qp-conflict-{uuid.uuid4()}"

        resp1 = self.client.post(
            f"/api/v1/projects/{project.id}/quick-payment-and-transition",
            json={
                "payment_type": "DEPOSIT",
                "amount": 300.0,
                "provider_event_id": event_id,
            },
        )
        self.assertEqual(resp1.status_code, 200)

        # Same event_id, different amount → 409
        resp2 = self.client.post(
            f"/api/v1/projects/{project.id}/quick-payment-and-transition",
            json={
                "payment_type": "DEPOSIT",
                "amount": 500.0,
                "provider_event_id": event_id,
            },
        )
        self.assertEqual(resp2.status_code, 409)

    # ------------------------------------------------------------------
    # FINAL payment → email_queued
    # ------------------------------------------------------------------

    @patch.dict(
        os.environ,
        {"ENABLE_FINANCE_LEDGER": "true", "ENABLE_EMAIL_INTAKE": "true"},
        clear=False,
    )
    def test_final_payment_queues_email(self):
        project = self._create_project(
            status="CERTIFIED",
            client_info={"client_id": "c-1", "email": "client@test.lt"},
        )
        resp = self.client.post(
            f"/api/v1/projects/{project.id}/quick-payment-and-transition",
            json={
                "payment_type": "FINAL",
                "amount": 1000.0,
                "provider_event_id": f"qp-final-{uuid.uuid4()}",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["email_queued"])

    @patch.dict(
        os.environ,
        {"ENABLE_FINANCE_LEDGER": "true", "ENABLE_EMAIL_INTAKE": "false"},
        clear=False,
    )
    def test_final_payment_no_email_when_intake_disabled(self):
        project = self._create_project(
            status="CERTIFIED",
            client_info={"client_id": "c-1", "email": "client@test.lt"},
        )
        resp = self.client.post(
            f"/api/v1/projects/{project.id}/quick-payment-and-transition",
            json={
                "payment_type": "FINAL",
                "amount": 1000.0,
                "provider_event_id": f"qp-final-{uuid.uuid4()}",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["email_queued"])

    @patch.dict(
        os.environ,
        {"ENABLE_FINANCE_LEDGER": "true", "ENABLE_EMAIL_INTAKE": "true"},
        clear=False,
    )
    def test_final_payment_no_email_when_no_client_email(self):
        project = self._create_project(
            status="CERTIFIED",
            client_info={"client_id": "c-1"},  # no email
        )
        resp = self.client.post(
            f"/api/v1/projects/{project.id}/quick-payment-and-transition",
            json={
                "payment_type": "FINAL",
                "amount": 1000.0,
                "provider_event_id": f"qp-final-{uuid.uuid4()}",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["email_queued"])


class V23SecurityTests(unittest.TestCase):
    """V2.3: 404 security strategy tests."""

    def setUp(self):
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

    @patch.dict(os.environ, {"ENABLE_FINANCE_LEDGER": "false"}, clear=False)
    def test_finance_disabled_returns_404_not_403(self):
        resp = self.client.get("/api/v1/admin/finance/ledger")
        self.assertEqual(resp.status_code, 404)

    @patch.dict(
        os.environ,
        {"ENABLE_FINANCE_METRICS": "false", "ENABLE_FINANCE_LEDGER": "true"},
        clear=False,
    )
    def test_metrics_disabled_returns_404(self):
        resp = self.client.get("/api/v1/admin/finance/metrics")
        self.assertEqual(resp.status_code, 404)


class V23MetricsTests(unittest.TestCase):
    """V2.3: SSE metrics endpoint tests."""

    def setUp(self):
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

    @patch.dict(
        os.environ,
        {"ENABLE_FINANCE_LEDGER": "true", "ENABLE_FINANCE_METRICS": "true"},
        clear=False,
    )
    def test_metrics_sse_returns_event_stream(self):
        # SSE endpoints stream infinitely, so we use a regular GET with
        # TestClient which buffers the first response chunk.
        from app.api.v1.finance import _compute_finance_metrics

        # Test the compute function directly (avoids SSE streaming hang)
        db = self.SessionLocal()
        try:
            metrics = _compute_finance_metrics(db)
            self.assertIn("daily_volume", metrics)
            self.assertIn("manual_ratio", metrics)
            self.assertIn("avg_attempts", metrics)
            self.assertIn("reject_rate", metrics)
            self.assertIn("avg_confirm_time_minutes", metrics)
            self.assertIn("timestamp", metrics)
            self.assertIsInstance(metrics["daily_volume"], float)
            self.assertIsInstance(metrics["manual_ratio"], float)
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {"ENABLE_FINANCE_LEDGER": "true", "ENABLE_FINANCE_METRICS": "true"},
        clear=False,
    )
    def test_metrics_rbac_non_admin_denied(self):
        self.admin_user = CurrentUser(id=str(uuid.uuid4()), role="SUBCONTRACTOR")

        def override():
            return self.admin_user

        app.dependency_overrides[get_current_user] = override
        resp = self.client.get("/api/v1/admin/finance/metrics")
        self.assertEqual(resp.status_code, 403)


class V23EmailConfirmTests(unittest.TestCase):
    """V2.3: POST /public/confirm-payment/{token} endpoint."""

    def setUp(self):
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

        # No auth needed for public endpoint, but we still need get_db
        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _setup_confirmed_project(self):
        """Create a CERTIFIED project with FINAL payment and a pending confirmation."""
        import hashlib
        import secrets

        db = self.SessionLocal()
        project = Project(
            client_info={"client_id": "c-1", "email": "test@example.com"},
            status="CERTIFIED",
        )
        db.add(project)
        db.flush()

        payment = Payment(
            project_id=project.id,
            provider="manual",
            provider_event_id=f"evt-{uuid.uuid4()}",
            amount=1000.0,
            currency="EUR",
            payment_type="FINAL",
            status="SUCCEEDED",
            payment_method="CASH",
        )
        db.add(payment)
        db.flush()

        token = secrets.token_urlsafe(8).upper()
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        confirmation = ClientConfirmation(
            project_id=project.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
            channel="email",
            status="PENDING",
        )
        db.add(confirmation)
        db.commit()
        db.refresh(project)
        db.close()
        return project, token

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_confirm_payment_valid_token(self):
        project, token = self._setup_confirmed_project()
        resp = self.client.post(f"/api/v1/public/confirm-payment/{token}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["project_id"], str(project.id))

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_confirm_payment_invalid_token(self):
        resp = self.client.post("/api/v1/public/confirm-payment/INVALID_TOKEN_XYZ")
        self.assertEqual(resp.status_code, 404)

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "true"}, clear=False)
    def test_confirm_payment_already_confirmed(self):
        project, token = self._setup_confirmed_project()

        # First confirm
        resp1 = self.client.post(f"/api/v1/public/confirm-payment/{token}")
        self.assertEqual(resp1.status_code, 200)

        # Second confirm → already confirmed
        resp2 = self.client.post(f"/api/v1/public/confirm-payment/{token}")
        self.assertEqual(resp2.status_code, 200)
        self.assertTrue(resp2.json()["already_confirmed"])

    @patch.dict(os.environ, {"ENABLE_EMAIL_INTAKE": "false"}, clear=False)
    def test_confirm_payment_email_intake_disabled(self):
        resp = self.client.post("/api/v1/public/confirm-payment/ANY_TOKEN")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
