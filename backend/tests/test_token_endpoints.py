from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID

import jwt
import pytest

from app.core.dependencies import SessionLocal
from app.models.project import Project, User

_SKIP_MSG = "SUPABASE_JWT_SECRET required for token endpoint tests"


def _decode(token: str) -> dict:
    secret = os.getenv("SUPABASE_JWT_SECRET", "")
    assert secret
    audience = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    return jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        audience=audience,
        options={"verify_aud": True},
    )


@pytest.mark.asyncio
async def test_admin_token_endpoint_issues_admin_jwt(client):
    r = await client.get("/api/v1/admin/token")
    # When feature flag is off, endpoint is intentionally hidden.
    if r.status_code == 404:
        pytest.skip("ADMIN_TOKEN_ENDPOINT_ENABLED=false")
    assert r.status_code == 200, r.text

    if not os.getenv("SUPABASE_JWT_SECRET"):
        pytest.skip(_SKIP_MSG)

    data = r.json()
    assert "token" in data
    assert "expires_at" in data
    payload = _decode(data["token"])
    assert payload["app_metadata"]["role"] == "ADMIN"
    assert payload["aud"] == os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated")


@pytest.mark.asyncio
async def test_admin_can_issue_contractor_token(client):
    if not os.getenv("SUPABASE_JWT_SECRET"):
        pytest.skip(_SKIP_MSG)

    user_id = UUID("00000000-0000-0000-0000-000000000101")
    assert SessionLocal is not None
    with SessionLocal() as db:
        if not db.get(User, user_id):
            db.add(
                User(
                    id=user_id,
                    email=f"{user_id}@test.local",
                    phone=None,
                    role="SUBCONTRACTOR",
                    is_active=True,
                )
            )
            db.commit()

    r = await client.get(f"/api/v1/admin/users/{user_id}/contractor-token")
    assert r.status_code == 200, r.text
    data = r.json()
    payload = _decode(data["token"])
    assert payload["sub"] == str(user_id)
    assert payload["app_metadata"]["role"] == "SUBCONTRACTOR"


@pytest.mark.asyncio
async def test_admin_can_issue_expert_token(client):
    if not os.getenv("SUPABASE_JWT_SECRET"):
        pytest.skip(_SKIP_MSG)

    user_id = UUID("00000000-0000-0000-0000-000000000102")
    assert SessionLocal is not None
    with SessionLocal() as db:
        if not db.get(User, user_id):
            db.add(
                User(
                    id=user_id,
                    email=f"{user_id}@test.local",
                    phone=None,
                    role="EXPERT",
                    is_active=True,
                )
            )
            db.commit()

    r = await client.get(f"/api/v1/admin/users/{user_id}/expert-token")
    assert r.status_code == 200, r.text
    data = r.json()
    payload = _decode(data["token"])
    assert payload["sub"] == str(user_id)
    assert payload["app_metadata"]["role"] == "EXPERT"


@pytest.mark.asyncio
async def test_admin_can_issue_client_token_for_project(client):
    if not os.getenv("SUPABASE_JWT_SECRET"):
        pytest.skip(_SKIP_MSG)

    # Create project via API, then inject client_id in DB (admin endpoint expects it).
    created = await client.post("/api/v1/projects", json={"name": "Token Project"})
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    project_uuid = UUID(project_id)

    client_id = "00000000-0000-0000-0000-000000000201"
    assert SessionLocal is not None
    with SessionLocal() as db:
        project = db.get(Project, project_uuid)
        assert project is not None
        info = dict(project.client_info or {})
        info["client_id"] = client_id
        info["email"] = "client@test.local"
        project.client_info = info
        db.commit()

    r = await client.get(f"/api/v1/admin/projects/{project_id}/client-token")
    assert r.status_code == 200, r.text
    data = r.json()
    payload = _decode(data["token"])
    assert payload["sub"] == client_id
    assert payload["app_metadata"]["role"] == "CLIENT"
    # sanity: exp is in the future
    assert int(payload["exp"]) > int(datetime.now(timezone.utc).timestamp())
