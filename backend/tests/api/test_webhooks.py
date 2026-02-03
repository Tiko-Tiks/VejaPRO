import pytest

@pytest.mark.asyncio
async def test_stripe_idempotent(client):
    payload = {"event_id":"evt_test_1","type":"deposit"}
    r1 = await client.post("/api/v1/webhook/stripe", json=payload)
    r2 = await client.post("/api/v1/webhook/stripe", json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
