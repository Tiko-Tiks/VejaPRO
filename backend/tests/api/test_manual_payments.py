import pytest


@pytest.mark.asyncio
async def test_manual_payment_idempotent(client):
    r = await client.post("/api/v1/projects", json={"name": "M Project"})
    pid = r.json()["id"]

    payload = {
        "payment_type": "DEPOSIT",
        "amount": 50.00,
        "currency": "EUR",
        "payment_method": "CASH",
        "provider_event_id": "CASH-TEST-IDEMPOTENT-1",
        "receipt_no": "CASH-TEST-IDEMPOTENT-1",
        "collection_context": "ON_SITE_BEFORE_WORK",
        "notes": "Testinis avansas",
    }

    p1 = await client.post(f"/api/v1/projects/{pid}/payments/manual", json=payload)
    assert p1.status_code == 201
    body1 = p1.json()
    assert body1["success"] is True
    assert body1["idempotent"] is False

    p2 = await client.post(f"/api/v1/projects/{pid}/payments/manual", json=payload)
    assert p2.status_code == 200
    body2 = p2.json()
    assert body2["success"] is True
    assert body2["idempotent"] is True
    assert body2["payment_id"] == body1["payment_id"]
