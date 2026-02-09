import pytest


@pytest.mark.asyncio
async def test_marketing_and_gallery(client):
    r = await client.post("/api/v1/projects", json={"name": "M Project"})
    pid = r.json()["id"]

    c = await client.post(f"/api/v1/projects/{pid}/marketing-consent")
    assert c.status_code == 200

    g = await client.get("/api/v1/gallery?limit=24")
    if g.status_code == 404:
        pytest.skip("Marketing module is disabled (ENABLE_MARKETING_MODULE=false)")
    assert g.status_code == 200
