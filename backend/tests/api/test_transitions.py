import pytest


@pytest.mark.asyncio
async def test_transition_happy_and_guard(client):
    r = await client.post("/api/v1/projects", json={"name": "T Project"})
    pid = r.json()["id"]

    # Cannot go to PAID without a DEPOSIT payment fact.
    bad_paid = await client.post(
        "/api/v1/transition-status", json={"entity_type": "project", "entity_id": pid, "new_status": "PAID"}
    )
    assert bad_paid.status_code == 400

    pay = await client.post(
        f"/api/v1/projects/{pid}/payments/manual",
        json={
            "payment_type": "DEPOSIT",
            "amount": 100.00,
            "currency": "EUR",
            "payment_method": "CASH",
            "provider_event_id": "CASH-TEST-1",
            "receipt_no": "CASH-TEST-1",
            "collection_context": "ON_SITE_BEFORE_WORK",
            "notes": "Testinis avansas",
        },
    )
    assert pay.status_code == 201

    ok = await client.post(
        "/api/v1/transition-status", json={"entity_type": "project", "entity_id": pid, "new_status": "PAID"}
    )
    assert ok.status_code == 200

    bad = await client.post(
        "/api/v1/transition-status",
        json={"entity_type": "project", "entity_id": pid, "new_status": "CERTIFIED", "actor": "SYSTEM"},
    )
    assert bad.status_code == 400

    idem = await client.post(
        "/api/v1/transition-status", json={"entity_type": "project", "entity_id": pid, "new_status": "PAID"}
    )
    assert idem.status_code == 200
