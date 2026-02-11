"""Admin UI V3 Diena 4 — Finance view, mini-triage, AI view tests."""

import os
import unittest
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import CurrentUser, get_current_user
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.main import app
from app.models.project import AuditLog, Base, Project


class FinanceViewTests(unittest.TestCase):
    """Tests for GET /admin/finance/view and /admin/finance/mini-triage."""

    def setUp(self):
        os.environ["ENABLE_FINANCE_LEDGER"] = "true"
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

        self.current_user = CurrentUser(id=str(uuid.uuid4()), role="ADMIN")

        def override_get_current_user():
            return self.current_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        os.environ.pop("ENABLE_FINANCE_LEDGER", None)
        get_settings.cache_clear()

    def _create_project(self, status: str):
        db = self.SessionLocal()
        project = Project(
            client_info={"client_id": str(uuid.uuid4()), "email": "a@b.lt"},
            status=status,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        db.close()
        return project

    def test_finance_view_returns_view_model(self):
        resp = self.client.get("/api/v1/admin/finance/view")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("items", data)
        self.assertIn("manual_payments_count_7d", data)
        self.assertIn("view_version", data)
        self.assertIsInstance(data["items"], list)

    def test_finance_mini_triage_includes_draft_without_deposit(self):
        p = self._create_project("DRAFT")
        resp = self.client.get("/api/v1/admin/finance/mini-triage", params={"limit": 10})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("items", data)
        ids = [item["project_id"] for item in data["items"]]
        self.assertIn(str(p.id), ids)

    def test_finance_mini_triage_includes_certified_without_final(self):
        p = self._create_project("CERTIFIED")
        resp = self.client.get("/api/v1/admin/finance/mini-triage", params={"limit": 10})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        ids = [item["project_id"] for item in data["items"]]
        self.assertIn(str(p.id), ids)


class AiViewTests(unittest.TestCase):
    """Tests for GET /admin/ai/view (low confidence attention)."""

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

        self.current_user = CurrentUser(id=str(uuid.uuid4()), role="ADMIN")

        def override_get_current_user():
            return self.current_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _create_ai_audit(self, confidence: float):
        db = self.SessionLocal()
        log = AuditLog(
            entity_type="ai",
            entity_id="intent",
            action="AI_RUN",
            new_value={"intent": "booking", "confidence": confidence},
            actor_type="SYSTEM",
            timestamp=datetime.now(timezone.utc),
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        db.close()
        return log

    def test_ai_view_returns_view_model(self):
        resp = self.client.get("/api/v1/admin/ai/view")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("low_confidence_count", data)
        self.assertIn("attention_items", data)
        self.assertIn("view_version", data)

    def test_ai_view_low_confidence_in_attention(self):
        self._create_ai_audit(0.3)
        self._create_ai_audit(0.8)
        resp = self.client.get("/api/v1/admin/ai/view")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(data["low_confidence_count"], 1)
        low_items = [i for i in data["attention_items"] if i["confidence"] < 0.5]
        self.assertGreaterEqual(len(low_items), 1)
