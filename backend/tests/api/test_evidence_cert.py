import pytest


@pytest.mark.asyncio
async def test_cert_guard(client):
    r = await client.post("/api/v1/projects", json={"name": "E Project"})
    pid = r.json()["id"]

    cert = await client.post("/api/v1/certify-project", json={"project_id": pid})
    assert cert.status_code == 400
