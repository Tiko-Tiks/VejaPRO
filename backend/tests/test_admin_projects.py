import unittest
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import CurrentUser, get_current_user
from app.core.dependencies import get_db
from app.main import app
from app.models.project import Base, Project


class AdminProjectsTests(unittest.TestCase):
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

    def _create_project(self, status: str, created_at: datetime):
        db = self.SessionLocal()
        project = Project(
            client_info={"client_id": "client-1"},
            status=status,
            created_at=created_at,
            updated_at=created_at,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        db.close()
        return project

    def test_admin_list_pagination_cursor(self):
        t1 = datetime.now(timezone.utc) - timedelta(minutes=3)
        t2 = datetime.now(timezone.utc) - timedelta(minutes=2)
        t3 = datetime.now(timezone.utc) - timedelta(minutes=1)
        p1 = self._create_project("DRAFT", t1)
        p2 = self._create_project("PAID", t2)
        p3 = self._create_project("SCHEDULED", t3)

        resp1 = self.client.get("/api/v1/admin/projects", params={"limit": 2})
        self.assertEqual(resp1.status_code, 200)
        body1 = resp1.json()
        ids_page1 = [item["id"] for item in body1["items"]]
        self.assertEqual(ids_page1, [str(p3.id), str(p2.id)])
        self.assertTrue(body1["has_more"])
        self.assertIsNotNone(body1["next_cursor"])

        resp2 = self.client.get(
            "/api/v1/admin/projects",
            params={"limit": 2, "cursor": body1["next_cursor"]},
        )
        self.assertEqual(resp2.status_code, 200)
        body2 = resp2.json()
        ids_page2 = [item["id"] for item in body2["items"]]
        self.assertEqual(ids_page2, [str(p1.id)])
        self.assertFalse(body2["has_more"])

    def test_admin_filter_by_status(self):
        self._create_project("DRAFT", datetime.now(timezone.utc) - timedelta(minutes=2))
        paid = self._create_project("PAID", datetime.now(timezone.utc) - timedelta(minutes=1))

        resp = self.client.get("/api/v1/admin/projects", params={"status": "PAID"})
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], str(paid.id))

    def test_non_admin_forbidden(self):
        self.current_user = CurrentUser(id=str(uuid.uuid4()), role="EXPERT")
        resp = self.client.get("/api/v1/admin/projects")
        self.assertEqual(resp.status_code, 403)

    # V3 view model (LOCK 1.1)
    def test_admin_projects_view_returns_view_model(self):
        t = datetime.now(timezone.utc) - timedelta(minutes=1)
        self._create_project("PAID", t)

        resp = self.client.get("/api/v1/admin/projects/view", params={"limit": 10})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("items", body)
        self.assertIn("view_version", body)
        self.assertIn("as_of", body)
        if body["items"]:
            item = body["items"][0]
            self.assertIn("id", item)
            self.assertIn("status", item)
            self.assertIn("client_masked", item)
            self.assertIn("attention_flags", item)
            self.assertIn("next_best_action", item)
            self.assertIn("last_activity", item)
            self.assertIn("stuck_reason", item)

    def test_admin_projects_view_attention_only_filter(self):
        self._create_project("DRAFT", datetime.now(timezone.utc) - timedelta(minutes=2))
        self._create_project("ACTIVE", datetime.now(timezone.utc) - timedelta(minutes=1))

        resp_all = self.client.get(
            "/api/v1/admin/projects/view",
            params={"attention_only": False, "limit": 20},
        )
        self.assertEqual(resp_all.status_code, 200)
        count_all = len(resp_all.json()["items"])

        resp_attention = self.client.get(
            "/api/v1/admin/projects/view",
            params={"attention_only": True, "limit": 20},
        )
        self.assertEqual(resp_attention.status_code, 200)
        count_attention = len(resp_attention.json()["items"])
        self.assertLessEqual(count_attention, count_all)

    def test_admin_projects_mini_triage_returns_cards(self):
        self._create_project("PAID", datetime.now(timezone.utc) - timedelta(minutes=1))
        self._create_project("SCHEDULED", datetime.now(timezone.utc) - timedelta(minutes=2))

        resp = self.client.get("/api/v1/admin/projects/mini-triage", params={"limit": 10})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("items", body)
        self.assertIn("view_version", body)
        for item in body["items"]:
            self.assertIn("project_id", item)
            self.assertIn("primary_action", item)
            pa = item["primary_action"]
            self.assertIn("label", pa)
            self.assertIn("action_key", pa)
            self.assertIn("payload", pa)

    def test_admin_projects_view_cursor_as_of_stable(self):
        t1 = datetime.now(timezone.utc) - timedelta(minutes=3)
        t2 = datetime.now(timezone.utc) - timedelta(minutes=2)
        t3 = datetime.now(timezone.utc) - timedelta(minutes=1)
        self._create_project("DRAFT", t1)
        self._create_project("PAID", t2)
        self._create_project("SCHEDULED", t3)

        resp1 = self.client.get(
            "/api/v1/admin/projects/view",
            params={"limit": 2, "attention_only": False},
        )
        self.assertEqual(resp1.status_code, 200)
        body1 = resp1.json()
        self.assertTrue(body1["has_more"])
        cursor = body1.get("next_cursor")
        as_of = body1.get("as_of")
        self.assertIsNotNone(cursor)
        self.assertIsNotNone(as_of)

        resp2 = self.client.get(
            "/api/v1/admin/projects/view",
            params={"limit": 5, "cursor": cursor, "as_of": as_of},
        )
        self.assertEqual(resp2.status_code, 200)
        body2 = resp2.json()
        self.assertEqual(body2["as_of"], as_of)

    def test_admin_projects_view_cursor_mismatch_returns_400(self):
        resp = self.client.get(
            "/api/v1/admin/projects/view",
            params={
                "limit": 2,
                "cursor": "aW52YWxpZC1jdXJzb3I=",
                "as_of": "2026-01-01T00:00:00+00:00",
            },
        )
        self.assertIn(resp.status_code, [400, 422])


if __name__ == "__main__":
    unittest.main()
