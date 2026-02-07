import unittest
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import CurrentUser, get_current_user
from app.core.dependencies import get_db
from app.main import app
from app.models.project import AuditLog, Base, Project, User


class AdminAssignTests(unittest.TestCase):
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

    def _create_project(self):
        db = self.SessionLocal()
        project = Project(client_info={"client_id": "client-1"}, status="DRAFT")
        db.add(project)
        db.commit()
        db.refresh(project)
        db.close()
        return project

    def _create_user(self, role: str):
        db = self.SessionLocal()
        user = User(email=f"{uuid.uuid4()}@example.com", role=role, created_at=datetime.now(timezone.utc))
        db.add(user)
        db.commit()
        db.refresh(user)
        db.close()
        return user

    def test_assign_contractor_success(self):
        project = self._create_project()
        contractor = self._create_user("SUBCONTRACTOR")

        resp = self.client.post(
            f"/api/v1/admin/projects/{project.id}/assign-contractor",
            json={"user_id": str(contractor.id)},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["no_change"], False)

        db = self.SessionLocal()
        refreshed = db.get(Project, project.id)
        logs = db.query(AuditLog).filter(AuditLog.entity_id == project.id, AuditLog.action == "ASSIGN_CONTRACTOR").all()
        self.assertEqual(str(refreshed.assigned_contractor_id), str(contractor.id))
        self.assertEqual(len(logs), 1)
        db.close()

    def test_assign_contractor_user_not_found(self):
        project = self._create_project()
        resp = self.client.post(
            f"/api/v1/admin/projects/{project.id}/assign-contractor",
            json={"user_id": str(uuid.uuid4())},
        )
        self.assertEqual(resp.status_code, 404)

    def test_assign_contractor_wrong_role(self):
        project = self._create_project()
        expert = self._create_user("EXPERT")
        resp = self.client.post(
            f"/api/v1/admin/projects/{project.id}/assign-contractor",
            json={"user_id": str(expert.id)},
        )
        self.assertEqual(resp.status_code, 400)

    def test_assign_contractor_no_change(self):
        project = self._create_project()
        contractor = self._create_user("SUBCONTRACTOR")

        self.client.post(
            f"/api/v1/admin/projects/{project.id}/assign-contractor",
            json={"user_id": str(contractor.id)},
        )
        resp = self.client.post(
            f"/api/v1/admin/projects/{project.id}/assign-contractor",
            json={"user_id": str(contractor.id)},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["no_change"], True)

    def test_assign_expert_success(self):
        project = self._create_project()
        expert = self._create_user("EXPERT")

        resp = self.client.post(
            f"/api/v1/admin/projects/{project.id}/assign-expert",
            json={"user_id": str(expert.id)},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["no_change"], False)

        db = self.SessionLocal()
        refreshed = db.get(Project, project.id)
        logs = db.query(AuditLog).filter(AuditLog.entity_id == project.id, AuditLog.action == "ASSIGN_EXPERT").all()
        self.assertEqual(str(refreshed.assigned_expert_id), str(expert.id))
        self.assertEqual(len(logs), 1)
        db.close()

    def test_assign_expert_wrong_role(self):
        project = self._create_project()
        contractor = self._create_user("SUBCONTRACTOR")
        resp = self.client.post(
            f"/api/v1/admin/projects/{project.id}/assign-expert",
            json={"user_id": str(contractor.id)},
        )
        self.assertEqual(resp.status_code, 400)

    def test_assign_expert_user_not_found(self):
        project = self._create_project()
        resp = self.client.post(
            f"/api/v1/admin/projects/{project.id}/assign-expert",
            json={"user_id": str(uuid.uuid4())},
        )
        self.assertEqual(resp.status_code, 404)

    def test_non_admin_forbidden(self):
        project = self._create_project()
        self.current_user = CurrentUser(id=str(uuid.uuid4()), role="EXPERT")
        resp = self.client.post(
            f"/api/v1/admin/projects/{project.id}/assign-expert",
            json={"user_id": str(uuid.uuid4())},
        )
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
