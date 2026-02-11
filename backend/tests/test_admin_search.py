"""Admin global search tests — LOCK 1.4: no PII in logs."""

import unittest
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import CurrentUser, get_current_user
from app.core.dependencies import get_db
from app.main import app
from app.models.project import Base, CallRequest, Project


class AdminSearchTests(unittest.TestCase):
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

    def _create_project(self, status="DRAFT"):
        db = self.SessionLocal()
        p = Project(client_info={"client_id": "c1"}, status=status)
        db.add(p)
        db.commit()
        db.refresh(p)
        db.close()
        return p

    def _create_call_request(self):
        db = self.SessionLocal()
        c = CallRequest(
            name="Test",
            phone="+37060000000",
            email="t@t.lt",
            status="NEW",
        )
        db.add(c)
        db.commit()
        db.refresh(c)
        db.close()
        return c

    def test_search_returns_items(self):
        p = self._create_project("DRAFT")
        prefix = str(p.id)[:8]
        resp = self.client.get("/api/v1/admin/search", params={"q": prefix, "limit": 10})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("items", data)
        self.assertGreaterEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["type"], "project")
        self.assertEqual(data["items"][0]["id"], str(p.id))

    def test_search_by_status(self):
        self._create_project("CERTIFIED")
        resp = self.client.get("/api/v1/admin/search", params={"q": "CERTIFIED", "limit": 10})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(len(data["items"]), 1)

    def test_non_admin_forbidden(self):
        self.current_user = CurrentUser(id=str(uuid.uuid4()), role="EXPERT")
        resp = self.client.get("/api/v1/admin/search", params={"q": "DRAFT"})
        self.assertEqual(resp.status_code, 403)
