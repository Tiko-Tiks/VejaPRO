import json
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.auth import CurrentUser, get_current_user
from app.core.config import Settings
from app.core.dependencies import get_db
from app.models.project import Base, Project, Evidence
import app.api.v1.projects as projects_module


def _setup():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine)

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    state = {
        "current_user": CurrentUser(id=str(uuid.uuid4()), role="EXPERT"),
        "settings": Settings(enable_marketing_module=True, enable_vision_ai=False),
    }

    def override_get_current_user():
        return state["current_user"]

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    orig_get_settings = projects_module.get_settings
    projects_module.get_settings = lambda: state["settings"]

    orig_upload_evidence = projects_module.upload_evidence_file
    projects_module.upload_evidence_file = lambda **kwargs: ("stub/path", "https://example.com/photo.jpg")

    client = TestClient(app)

    def cleanup():
        client.close()
        app.dependency_overrides.clear()
        projects_module.get_settings = orig_get_settings
        projects_module.upload_evidence_file = orig_upload_evidence
        Base.metadata.drop_all(engine)
        engine.dispose()

    return state, session_local, client, cleanup


def _create_project(session_local, *, status="CERTIFIED", marketing_consent=True):
    db = session_local()
    project = Project(
        client_info={"client_id": "client-1"},
        status=status,
        marketing_consent=marketing_consent,
        marketing_consent_at=datetime.now(timezone.utc) if marketing_consent else None,
        is_certified=status in {"CERTIFIED", "ACTIVE"},
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    db.close()
    return project


def _create_evidence(session_local, project_id, category="EXPERT_CERTIFICATION"):
    db = session_local()
    evidence = Evidence(
        project_id=project_id,
        file_url="https://example.com/after.jpg",
        category=category,
        show_on_web=False,
        is_featured=False,
        location_tag=None,
    )
    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    db.close()
    return evidence


def test_gallery_disabled_returns_404():
    state, session_local, client, cleanup = _setup()
    try:
        state["settings"] = Settings(enable_marketing_module=False)
        resp = client.get("/api/v1/gallery")
        assert resp.status_code == 404
    finally:
        cleanup()


def test_approve_for_web_disabled_returns_404():
    state, session_local, client, cleanup = _setup()
    try:
        state["settings"] = Settings(enable_marketing_module=False)
        project = _create_project(session_local)
        evidence = _create_evidence(session_local, project.id)
        resp = client.post(f"/api/v1/evidences/{evidence.id}/approve-for-web")
        assert resp.status_code == 404
    finally:
        cleanup()


def test_approve_for_web_requires_consent():
    state, session_local, client, cleanup = _setup()
    try:
        state["settings"] = Settings(enable_marketing_module=True)
        project = _create_project(session_local, status="CERTIFIED", marketing_consent=False)
        evidence = _create_evidence(session_local, project.id)
        resp = client.post(f"/api/v1/evidences/{evidence.id}/approve-for-web")
        assert resp.status_code == 400
    finally:
        cleanup()


def test_approve_for_web_requires_certified_status():
    state, session_local, client, cleanup = _setup()
    try:
        state["settings"] = Settings(enable_marketing_module=True)
        project = _create_project(session_local, status="PAID", marketing_consent=True)
        evidence = _create_evidence(session_local, project.id)
        resp = client.post(f"/api/v1/evidences/{evidence.id}/approve-for-web")
        assert resp.status_code == 400
    finally:
        cleanup()


def test_approve_for_web_requires_role():
    state, session_local, client, cleanup = _setup()
    try:
        state["settings"] = Settings(enable_marketing_module=True)
        state["current_user"] = CurrentUser(id=str(uuid.uuid4()), role="CLIENT")
        project = _create_project(session_local, status="CERTIFIED", marketing_consent=True)
        evidence = _create_evidence(session_local, project.id)
        resp = client.post(f"/api/v1/evidences/{evidence.id}/approve-for-web")
        assert resp.status_code == 403
    finally:
        cleanup()


def test_approve_for_web_success():
    state, session_local, client, cleanup = _setup()
    try:
        state["settings"] = Settings(enable_marketing_module=True)
        state["current_user"] = CurrentUser(id=str(uuid.uuid4()), role="EXPERT")
        project = _create_project(session_local, status="CERTIFIED", marketing_consent=True)
        evidence = _create_evidence(session_local, project.id)
        resp = client.post(
            f"/api/v1/evidences/{evidence.id}/approve-for-web",
            json={"location_tag": "Vilnius", "is_featured": True},
        )
        assert resp.status_code == 200
    finally:
        cleanup()


def test_vision_ai_disabled_no_analysis():
    state, session_local, client, cleanup = _setup()
    try:
        state["settings"] = Settings(enable_vision_ai=False)
        state["current_user"] = CurrentUser(id=str(uuid.uuid4()), role="SUBCONTRACTOR")
        project = _create_project(session_local, status="DRAFT", marketing_consent=False)
        resp = client.post(
            "/api/v1/upload-evidence",
            data={"project_id": str(project.id), "category": "SITE_BEFORE"},
            files={"file": ("photo.jpg", b"data", "image/jpeg")},
        )
        assert resp.status_code == 200

        db = session_local()
        refreshed = db.get(Project, project.id)
        assert refreshed.vision_analysis is None
        db.close()
    finally:
        cleanup()


def test_vision_ai_enabled_writes_analysis():
    state, session_local, client, cleanup = _setup()
    try:
        state["settings"] = Settings(enable_vision_ai=True)
        state["current_user"] = CurrentUser(id=str(uuid.uuid4()), role="SUBCONTRACTOR")
        project = _create_project(session_local, status="DRAFT", marketing_consent=False)
        resp = client.post(
            "/api/v1/upload-evidence",
            data={"project_id": str(project.id), "category": "SITE_BEFORE"},
            files={"file": ("photo.jpg", b"data", "image/jpeg")},
        )
        assert resp.status_code == 200

        db = session_local()
        refreshed = db.get(Project, project.id)
        analysis = refreshed.vision_analysis
        db.close()
        assert analysis is not None
        if isinstance(analysis, str):
            analysis = json.loads(analysis)
        assert "generated_by_ai" in analysis
        assert "confidence" in analysis
        assert "model" in analysis
        assert "timestamp" in analysis
    finally:
        cleanup()
