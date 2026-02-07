import pytest


@pytest.mark.asyncio
async def test_stripe_idempotent(client):
    payload = {"event_id": "evt_test_1", "type": "deposit"}
    r1 = await client.post("/api/v1/webhook/stripe", json=payload)
    r2 = await client.post("/api/v1/webhook/stripe", json=payload)
    # Stripe is optional. When disabled, webhook should not be available.
    assert r1.status_code == 404
    assert r2.status_code == 404
