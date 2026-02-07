import pytest


@pytest.mark.asyncio
async def test_create_project(client):
    r = await client.post("/api/v1/projects", json={"name":"Smoke Project"})
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "DRAFT"
    assert "id" in data

@pytest.mark.asyncio
async def test_get_project_and_audit(client):
    r = await client.post("/api/v1/projects", json={"name":"Audit Project"})
    pid = r.json()["id"]
    g = await client.get(f"/api/v1/projects/{pid}")
    assert g.status_code == 200
