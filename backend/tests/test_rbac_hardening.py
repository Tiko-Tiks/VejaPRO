import unittest
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.v1.projects as projects_module
from app.core.auth import CurrentUser, get_current_user
from app.core.dependencies import get_db
from app.main import app
from app.models.project import Base, Evidence, Project


class RbacHardeningTests(unittest.TestCase):
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

        self.orig_upload_image_variants = projects_module.upload_image_variants

        class _StubUploaded:
            original_url = "https://example.com/photo.jpg"
            thumbnail_url = "https://example.com/photo_thumb.webp"
            medium_url = "https://example.com/photo_md.webp"

        projects_module.upload_image_variants = lambda **kwargs: _StubUploaded()

        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        projects_module.upload_image_variants = self.orig_upload_image_variants
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _create_project(
        self,
        *,
        status: str = "DRAFT",
        client_id: str = "client-1",
        assigned_contractor_id: str | None = None,
        assigned_expert_id: str | None = None,
        marketing_consent: bool = False,
    ) -> Project:
        db = self.SessionLocal()
        project = Project(
            client_info={"client_id": client_id, "name": "Client"},
            status=status,
            assigned_contractor_id=assigned_contractor_id,
            assigned_expert_id=assigned_expert_id,
            marketing_consent=marketing_consent,
            is_certified=status in {"CERTIFIED", "ACTIVE"},
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        db.close()
        return project

    def _seed_cert_evidence(self, project_id: str, count: int = 3):
        db = self.SessionLocal()
        for _ in range(count):
            db.add(
                Evidence(
                    project_id=project_id,
                    file_url="https://example.com/cert.jpg",
                    category="EXPERT_CERTIFICATION",
                    show_on_web=False,
                )
            )
        db.commit()
        db.close()

    def test_transition_requires_assignment_for_subcontractor(self):
        contractor_id = str(uuid.uuid4())
        project = self._create_project(status="PAID", assigned_contractor_id=str(uuid.uuid4()))
        self.current_user = CurrentUser(id=contractor_id, role="SUBCONTRACTOR")

        resp = self.client.post(
            "/api/v1/transition-status",
            json={"project_id": str(project.id), "new_status": "SCHEDULED"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_upload_expert_certification_forbidden_for_subcontractor(self):
        contractor_id = str(uuid.uuid4())
        project = self._create_project(status="SCHEDULED", assigned_contractor_id=contractor_id)
        self.current_user = CurrentUser(id=contractor_id, role="SUBCONTRACTOR")

        resp = self.client.post(
            "/api/v1/upload-evidence",
            data={"project_id": str(project.id), "category": "EXPERT_CERTIFICATION"},
            files={"file": ("photo.jpg", b"data", "image/jpeg")},
        )
        self.assertEqual(resp.status_code, 403)

    def test_upload_site_before_forbidden_for_expert(self):
        expert_id = str(uuid.uuid4())
        project = self._create_project(status="PENDING_EXPERT", assigned_expert_id=expert_id)
        self.current_user = CurrentUser(id=expert_id, role="EXPERT")

        resp = self.client.post(
            "/api/v1/upload-evidence",
            data={"project_id": str(project.id), "category": "SITE_BEFORE"},
            files={"file": ("photo.jpg", b"data", "image/jpeg")},
        )
        self.assertEqual(resp.status_code, 403)

    def test_certify_requires_assigned_expert(self):
        assigned_expert = str(uuid.uuid4())
        current_expert = str(uuid.uuid4())
        project = self._create_project(status="PENDING_EXPERT", assigned_expert_id=assigned_expert)
        self._seed_cert_evidence(str(project.id))
        self.current_user = CurrentUser(id=current_expert, role="EXPERT")

        resp = self.client.post(
            "/api/v1/certify-project",
            json={
                "project_id": str(project.id),
                "checklist": {
                    "ground": True,
                    "seed": True,
                    "edges": True,
                    "robot": True,
                    "perimeter": True,
                    "cleanliness": True,
                },
            },
        )
        self.assertEqual(resp.status_code, 403)

    def test_marketing_consent_requires_project_owner_for_client(self):
        project = self._create_project(status="CERTIFIED", client_id="client-1", marketing_consent=False)
        self.current_user = CurrentUser(id="client-2", role="CLIENT")

        resp = self.client.post(f"/api/v1/projects/{project.id}/marketing-consent", json={"consent": True})
        self.assertEqual(resp.status_code, 403)

    def test_certify_rejects_incomplete_checklist(self):
        expert_id = str(uuid.uuid4())
        project = self._create_project(status="PENDING_EXPERT", assigned_expert_id=expert_id)
        self._seed_cert_evidence(str(project.id))
        self.current_user = CurrentUser(id=expert_id, role="EXPERT")

        resp = self.client.post(
            "/api/v1/certify-project",
            json={
                "project_id": str(project.id),
                "checklist": {"ground": True, "seed": False},
            },
        )
        self.assertEqual(resp.status_code, 400)

    def test_certificate_endpoint_requires_auth(self):
        project = self._create_project(status="CERTIFIED", marketing_consent=True)

        app.dependency_overrides.pop(get_current_user, None)
        unauth_client = TestClient(app)
        try:
            resp = unauth_client.get(f"/api/v1/projects/{project.id}/certificate")
        finally:
            unauth_client.close()

        self.assertEqual(resp.status_code, 401)
