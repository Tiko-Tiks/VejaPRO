import pytest

@pytest.mark.asyncio
async def test_transition_happy_and_guard(client):
    r = await client.post("/api/v1/projects", json={"name":"T Project"})
    pid = r.json()["id"]

    ok = await client.post("/api/v1/transition-status", json={
        "entity_type":"project","entity_id":pid,
        "new_status":"PAID","actor":"SYSTEM_STRIPE"
    })
    assert ok.status_code == 200

    bad = await client.post("/api/v1/transition-status", json={
        "entity_type":"project","entity_id":pid,
        "new_status":"CERTIFIED","actor":"SYSTEM"
    })
    assert bad.status_code == 400

    idem = await client.post("/api/v1/transition-status", json={
        "entity_type":"project","entity_id":pid,
        "new_status":"PAID","actor":"SYSTEM_STRIPE"
    })
    assert idem.status_code == 200
