import unittest
from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.auth import CurrentUser, get_current_user
from app.core.dependencies import get_db
from app.models.project import Base, Project, AuditLog


class AuditLogTests(unittest.TestCase):
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

    def _create_project(self, assigned_expert_id=None, assigned_contractor_id=None):
        db = self.SessionLocal()
        project = Project(
            client_info={"client_id": "client-1"},
            status="DRAFT",
            assigned_expert_id=assigned_expert_id,
            assigned_contractor_id=assigned_contractor_id,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        db.close()
        return project

    def _create_audit_log(self, entity_id, action, actor_type="ADMIN", ts=None, entity_type="project"):
        db = self.SessionLocal()
        log = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_type=actor_type,
            timestamp=ts or datetime.now(timezone.utc),
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        db.close()
        return log

    def test_admin_pagination_and_cursor(self):
        project = self._create_project()
        t1 = datetime.now(timezone.utc) - timedelta(minutes=3)
        t2 = datetime.now(timezone.utc) - timedelta(minutes=2)
        t3 = datetime.now(timezone.utc) - timedelta(minutes=1)

        log1 = self._create_audit_log(project.id, "A1", ts=t1)
        log2 = self._create_audit_log(project.id, "A2", ts=t2)
        log3 = self._create_audit_log(project.id, "A3", ts=t3)

        resp1 = self.client.get("/api/v1/audit-logs", params={"limit": 2})
        self.assertEqual(resp1.status_code, 200)
        body1 = resp1.json()
        self.assertEqual(len(body1["items"]), 2)
        ids_page1 = [item["id"] for item in body1["items"]]
        self.assertEqual(ids_page1[0], str(log3.id))
        self.assertEqual(ids_page1[1], str(log2.id))
        self.assertTrue(body1["has_more"])
        self.assertIsNotNone(body1["next_cursor"])

        resp2 = self.client.get("/api/v1/audit-logs", params={"limit": 2, "cursor": body1["next_cursor"]})
        self.assertEqual(resp2.status_code, 200)
        body2 = resp2.json()
        ids_page2 = [item["id"] for item in body2["items"]]
        self.assertEqual(ids_page2, [str(log1.id)])
        self.assertFalse(body2["has_more"])

    def test_expert_only_assigned_projects(self):
        expert_id = str(uuid.uuid4())
        project_allowed = self._create_project(assigned_expert_id=expert_id)
        project_denied = self._create_project(assigned_expert_id=str(uuid.uuid4()))
        self._create_audit_log(project_allowed.id, "STATUS_CHANGE", actor_type="EXPERT")
        self._create_audit_log(project_denied.id, "STATUS_CHANGE", actor_type="EXPERT")

        self.current_user = CurrentUser(id=expert_id, role="EXPERT")
        resp = self.client.get("/api/v1/audit-logs")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["entity_id"], str(project_allowed.id))

        resp_denied = self.client.get("/api/v1/audit-logs", params={"entity_id": str(project_denied.id)})
        self.assertEqual(resp_denied.status_code, 403)

    def test_subcontractor_only_assigned_projects(self):
        contractor_id = str(uuid.uuid4())
        project_allowed = self._create_project(assigned_contractor_id=contractor_id)
        project_denied = self._create_project(assigned_contractor_id=str(uuid.uuid4()))
        self._create_audit_log(project_allowed.id, "STATUS_CHANGE", actor_type="SUBCONTRACTOR")
        self._create_audit_log(project_denied.id, "STATUS_CHANGE", actor_type="SUBCONTRACTOR")

        self.current_user = CurrentUser(id=contractor_id, role="SUBCONTRACTOR")
        resp = self.client.get("/api/v1/audit-logs")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["entity_id"], str(project_allowed.id))

        resp_denied = self.client.get("/api/v1/audit-logs", params={"entity_id": str(project_denied.id)})
        self.assertEqual(resp_denied.status_code, 403)

    def test_other_role_forbidden(self):
        self.current_user = CurrentUser(id=str(uuid.uuid4()), role="CLIENT")
        resp = self.client.get("/api/v1/audit-logs")
        self.assertEqual(resp.status_code, 403)

    def test_invalid_cursor_returns_400(self):
        resp = self.client.get("/api/v1/audit-logs", params={"cursor": "not-base64"})
        self.assertEqual(resp.status_code, 400)

    def test_from_ts_greater_than_to_ts_returns_400(self):
        now = datetime.now(timezone.utc)
        resp = self.client.get(
            "/api/v1/audit-logs",
            params={"from_ts": (now + timedelta(hours=1)).isoformat(), "to_ts": now.isoformat()},
        )
        self.assertEqual(resp.status_code, 400)

    def test_filter_combination(self):
        project = self._create_project()
        t1 = datetime.now(timezone.utc) - timedelta(hours=2)
        t2 = datetime.now(timezone.utc) - timedelta(hours=1)

        self._create_audit_log(project.id, "STATUS_CHANGE", actor_type="ADMIN", ts=t1)
        self._create_audit_log(project.id, "UPLOAD_EVIDENCE", actor_type="EXPERT", ts=t2)

        resp = self.client.get(
            "/api/v1/audit-logs",
            params={
                "action": "UPLOAD_EVIDENCE",
                "actor_type": "EXPERT",
                "from_ts": (t2 - timedelta(minutes=1)).isoformat(),
                "to_ts": (t2 + timedelta(minutes=1)).isoformat(),
            },
        )
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["action"], "UPLOAD_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
