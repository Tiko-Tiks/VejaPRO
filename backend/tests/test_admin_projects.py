import unittest
from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.auth import CurrentUser, get_current_user
from app.core.dependencies import get_db
from app.models.project import Base, Project


class AdminProjectsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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

        resp2 = self.client.get("/api/v1/admin/projects", params={"limit": 2, "cursor": body1["next_cursor"]})
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


if __name__ == "__main__":
    unittest.main()
