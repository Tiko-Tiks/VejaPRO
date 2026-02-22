"""Tests for V2 estimate pricing engine and endpoints."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from tests.conftest import _build_auth_header, _make_asgi_client

# ─── Unit tests: estimate_rules.py ────────────────────────────────────────


class TestGetRate:
    def test_sejimas_small_area(self):
        from app.services.estimate_rules import get_rate

        assert get_rate("vejos_irengimas", "sejimas", 100) == 5.00

    def test_sejimas_medium_area(self):
        from app.services.estimate_rules import get_rate

        assert get_rate("vejos_irengimas", "sejimas", 300) == 4.50

    def test_sejimas_large_area(self):
        from app.services.estimate_rules import get_rate

        assert get_rate("vejos_irengimas", "sejimas", 600) == 4.00

    def test_sejimas_xlarge_area(self):
        from app.services.estimate_rules import get_rate

        assert get_rate("vejos_irengimas", "sejimas", 1000) == 3.50

    def test_ritinine_boundary(self):
        from app.services.estimate_rules import get_rate

        assert get_rate("vejos_irengimas", "ritinine", 200) == 9.00
        assert get_rate("vejos_irengimas", "ritinine", 201) == 8.00

    def test_hidroseija(self):
        from app.services.estimate_rules import get_rate

        assert get_rate("vejos_irengimas", "hidroseija", 50) == 4.00
        assert get_rate("vejos_irengimas", "hidroseija", 900) == 2.80

    def test_apleisto_mazas(self):
        from app.services.estimate_rules import get_rate

        assert get_rate("apleisto_sklypo_tvarkymas", "mazas", 100) == 3.00
        assert get_rate("apleisto_sklypo_tvarkymas", "mazas", 1000) == 2.00

    def test_apleisto_didelis(self):
        from app.services.estimate_rules import get_rate

        assert get_rate("apleisto_sklypo_tvarkymas", "didelis", 100) == 6.00
        assert get_rate("apleisto_sklypo_tvarkymas", "didelis", 500) == 4.50

    def test_unknown_service_raises(self):
        from app.services.estimate_rules import get_rate

        with pytest.raises(ValueError, match="Unknown service"):
            get_rate("unknown_service", "sejimas", 100)

    def test_unknown_method_raises(self):
        from app.services.estimate_rules import get_rate

        with pytest.raises(ValueError, match="Unknown method"):
            get_rate("vejos_irengimas", "unknown_method", 100)


class TestComputePrice:
    def test_basic_calculation(self):
        from app.services.estimate_rules import compute_price

        result = compute_price("vejos_irengimas", "sejimas", 300, km_one_way=25, mole_net=True)
        assert result["rate_eur_m2"] == 4.50
        assert result["base_eur"] == 1350.00  # 300 * 4.50
        assert result["transport_eur"] == 50.00  # max(50, 25*1.50=37.50) = 50
        assert result["mole_net_eur"] == 450.00  # 300 * 1.50
        assert result["total_eur"] == 1850.00  # 1350 + 50 + 450

    def test_zero_km_minimum_transport(self):
        from app.services.estimate_rules import compute_price

        result = compute_price("vejos_irengimas", "sejimas", 100, km_one_way=0)
        assert result["transport_eur"] == 50.00

    def test_high_km_transport(self):
        from app.services.estimate_rules import compute_price

        result = compute_price("vejos_irengimas", "sejimas", 100, km_one_way=100)
        assert result["transport_eur"] == 150.00  # 100 * 1.50

    def test_no_mole_net(self):
        from app.services.estimate_rules import compute_price

        result = compute_price("vejos_irengimas", "sejimas", 100, mole_net=False)
        assert result["mole_net_eur"] == 0.0

    def test_large_area(self):
        from app.services.estimate_rules import compute_price

        result = compute_price("vejos_irengimas", "sejimas", 2000, km_one_way=0)
        assert result["rate_eur_m2"] == 3.50
        assert result["base_eur"] == 7000.00

    def test_breakdown_structure(self):
        from app.services.estimate_rules import compute_price

        result = compute_price("vejos_irengimas", "sejimas", 100, km_one_way=10, mole_net=True)
        assert len(result["breakdown"]) == 3
        assert result["breakdown"][0]["label"] == "Bazine kaina"
        assert result["breakdown"][1]["label"] == "Transportas"
        assert result["breakdown"][2]["label"] == "Kurmiu tinklas"

    def test_breakdown_without_mole_net(self):
        from app.services.estimate_rules import compute_price

        result = compute_price("vejos_irengimas", "sejimas", 100)
        assert len(result["breakdown"]) == 2

    def test_rules_version_in_result(self):
        from app.services.estimate_rules import CURRENT_RULES_VERSION, compute_price

        result = compute_price("vejos_irengimas", "sejimas", 100)
        assert result["rules_version"] == CURRENT_RULES_VERSION


class TestGetRules:
    def test_structure(self):
        from app.services.estimate_rules import get_rules

        rules = get_rules()
        assert rules["rules_version"] == "v2"
        assert "vejos_irengimas" in rules["services"]
        assert "apleisto_sklypo_tvarkymas" in rules["services"]
        assert len(rules["addons"]) == 1
        assert rules["addons"][0]["key"] == "mole_net"
        assert rules["addons"][0].get("pricing_mode") == "included_in_estimate"
        assert "transport" in rules
        assert "disclaimer" in rules

    def test_services_have_methods(self):
        from app.services.estimate_rules import get_rules

        rules = get_rules()
        vejos = rules["services"]["vejos_irengimas"]
        assert "sejimas" in vejos["methods"]
        assert "ritinine" in vejos["methods"]
        assert "hidroseija" in vejos["methods"]

    def test_methods_have_tiers(self):
        from app.services.estimate_rules import get_rules

        rules = get_rules()
        sejimas = rules["services"]["vejos_irengimas"]["methods"]["sejimas"]
        assert len(sejimas["tiers"]) == 4


# ─── Integration tests: API endpoints ────────────────────────────────────


async def _fresh_client_user():
    """Create a client user with a unique sub (avoids duplicate estimate check)."""
    import os

    unique_sub = str(uuid.uuid4())
    os.environ["TEST_AUTH_SUB"] = unique_sub
    headers = _build_auth_header(role="CLIENT")
    os.environ.pop("TEST_AUTH_SUB", None)
    c = await _make_asgi_client(headers)
    return c


@pytest_asyncio.fixture
async def client_user():
    c = await _fresh_client_user()
    async with c:
        yield c


@pytest_asyncio.fixture
async def admin_user():
    headers = _build_auth_header(role="ADMIN")
    c = await _make_asgi_client(headers)
    async with c:
        yield c


@pytest.mark.asyncio
async def test_get_estimate_rules(client_user):
    resp = await client_user.get("/api/v1/client/estimate/rules")
    assert resp.status_code == 200
    data = resp.json()
    assert data["rules_version"] == "v2"
    assert "vejos_irengimas" in data["services"]
    assert "apleisto_sklypo_tvarkymas" in data["services"]
    assert len(data["addons"]) == 1
    assert data["addons"][0]["key"] == "mole_net"
    assert "transport" in data
    assert data["disclaimer"]


@pytest.mark.asyncio
async def test_post_estimate_price(client_user):
    resp = await client_user.post(
        "/api/v1/client/estimate/price",
        json={
            "rules_version": "v2",
            "service": "vejos_irengimas",
            "method": "sejimas",
            "area_m2": 300,
            "km_one_way": 25,
            "mole_net": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["base_eur"] == 1350.0
    assert data["transport_eur"] == 50.0
    assert data["mole_net_eur"] == 450.0
    assert data["total_eur"] == 1850.0
    assert data["rate_eur_m2"] == 4.5


@pytest.mark.asyncio
async def test_post_estimate_price_stale_version(client_user):
    from app.services.estimate_rules import CURRENT_RULES_VERSION

    resp = await client_user.post(
        "/api/v1/client/estimate/price",
        json={
            "rules_version": "v1",
            "service": "vejos_irengimas",
            "method": "sejimas",
            "area_m2": 100,
        },
    )
    assert resp.status_code == 409
    data = resp.json()
    assert data["detail"]["code"] == "RULES_VERSION_STALE"
    assert data["detail"].get("expected_rules_version") == CURRENT_RULES_VERSION


@pytest.mark.asyncio
async def test_post_estimate_submit_stale_version_409(client_user):
    from app.services.estimate_rules import CURRENT_RULES_VERSION

    resp = await client_user.post(
        "/api/v1/client/estimate/submit",
        json={
            "rules_version": "v1",
            "service": "vejos_irengimas",
            "method": "sejimas",
            "area_m2": 100,
            "phone": "+37060000001",
            "address": "Vilnius, Test 1",
        },
    )
    assert resp.status_code == 409
    data = resp.json()
    assert data["detail"]["code"] == "RULES_VERSION_STALE"
    assert data["detail"].get("expected_rules_version") == CURRENT_RULES_VERSION


@pytest.mark.asyncio
async def test_post_estimate_price_unknown_service(client_user):
    resp = await client_user.post(
        "/api/v1/client/estimate/price",
        json={
            "rules_version": "v2",
            "service": "nonexistent",
            "method": "sejimas",
            "area_m2": 100,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_estimate_price_addons_selected_vs_empty(client_user):
    """V3: same base_range, addons_selected=[] vs ['mole_net'] — total differs."""
    base = {
        "rules_version": "v2",
        "service": "vejos_irengimas",
        "method": "sejimas",
        "area_m2": 300,
        "km_one_way": 0,
    }
    resp_empty = await client_user.post(
        "/api/v1/client/estimate/price",
        json={**base, "addons_selected": []},
    )
    assert resp_empty.status_code == 200
    total_empty = resp_empty.json()["total_eur"]
    resp_mole = await client_user.post(
        "/api/v1/client/estimate/price",
        json={**base, "addons_selected": ["mole_net"]},
    )
    assert resp_mole.status_code == 200
    total_mole = resp_mole.json()["total_eur"]
    assert total_mole > total_empty
    assert resp_mole.json()["mole_net_eur"] > 0
    assert resp_empty.json()["mole_net_eur"] == 0.0


@pytest.mark.asyncio
async def test_post_estimate_price_legacy_mole_net_equivalent(client_user):
    """V3: mole_net=true equivalent to addons_selected=['mole_net']."""
    base = {
        "rules_version": "v2",
        "service": "vejos_irengimas",
        "method": "sejimas",
        "area_m2": 100,
        "km_one_way": 5,
    }
    resp_legacy = await client_user.post(
        "/api/v1/client/estimate/price",
        json={**base, "mole_net": True},
    )
    resp_v3 = await client_user.post(
        "/api/v1/client/estimate/price",
        json={**base, "addons_selected": ["mole_net"]},
    )
    assert resp_legacy.status_code == 200
    assert resp_v3.status_code == 200
    assert resp_legacy.json()["total_eur"] == resp_v3.json()["total_eur"]
    assert resp_legacy.json()["mole_net_eur"] == resp_v3.json()["mole_net_eur"]


@pytest.mark.asyncio
async def test_post_estimate_price_unknown_addon_400(client_user):
    """V3: unknown addon key in addons_selected returns 400."""
    resp = await client_user.post(
        "/api/v1/client/estimate/price",
        json={
            "rules_version": "v2",
            "service": "vejos_irengimas",
            "method": "sejimas",
            "area_m2": 100,
            "addons_selected": ["mole_net", "unknown_addon"],
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data.get("detail", {}).get("code") == "UNKNOWN_ADDON"


@pytest.mark.asyncio
async def test_post_estimate_price_area_tiers_eur_per_m2_decreases(client_user):
    """Ploto pakopos: larger area has lower rate_eur_m2."""
    base = {
        "rules_version": "v2",
        "service": "vejos_irengimas",
        "method": "sejimas",
        "km_one_way": 0,
        "addons_selected": [],
    }
    resp_500 = await client_user.post(
        "/api/v1/client/estimate/price",
        json={**base, "area_m2": 500},
    )
    resp_5000 = await client_user.post(
        "/api/v1/client/estimate/price",
        json={**base, "area_m2": 5000},
    )
    assert resp_500.status_code == 200
    assert resp_5000.status_code == 200
    rate_500 = resp_500.json()["rate_eur_m2"]
    rate_5000 = resp_5000.json()["rate_eur_m2"]
    assert rate_5000 < rate_500


@pytest.mark.asyncio
async def test_post_estimate_submit(client_user):
    resp = await client_user.post(
        "/api/v1/client/estimate/submit",
        json={
            "rules_version": "v2",
            "service": "vejos_irengimas",
            "method": "sejimas",
            "area_m2": 200,
            "km_one_way": 10,
            "mole_net": False,
            "phone": "+37060000000",
            "address": "Vilnius, Gedimino pr. 1",
            "slope_flag": False,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["project_id"]
    assert data["message"]
    assert "price_result" in data
    assert data["price_result"]["total_eur"] > 0


@pytest.mark.asyncio
async def test_post_estimate_submit_creates_draft_with_quote_pending(client_user, admin_user):
    resp = await client_user.post(
        "/api/v1/client/estimate/submit",
        json={
            "rules_version": "v2",
            "service": "vejos_irengimas",
            "method": "ritinine",
            "area_m2": 500,
            "km_one_way": 30,
            "addons_selected": ["mole_net"],
            "phone": "+37061111111",
            "address": "Kaunas, Laisves al. 5",
            "slope_flag": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    project_id = data["project_id"]
    assert data.get("price_result") is not None
    submit_total = data["price_result"]["total_eur"]

    proj_resp = await admin_user.get(f"/api/v1/projects/{project_id}")
    assert proj_resp.status_code == 200
    proj = proj_resp.json()["project"]
    assert proj["status"] == "DRAFT"
    ci = proj["client_info"]
    assert ci["quote_pending"] is True
    est = ci["estimate"]
    assert est["service"] == "vejos_irengimas"
    assert est["method"] == "ritinine"
    assert est["area_m2"] == 500
    assert est["km_one_way"] == 30
    assert est["mole_net"] is True
    assert est.get("addons_selected") == ["mole_net"]
    assert est.get("price_result") is not None
    assert est["price_result"]["total_eur"] == submit_total
    assert est["rules_version"] == "v2"


@pytest.mark.asyncio
async def test_admin_final_quote(client_user, admin_user):
    # Create project via estimate submit
    resp = await client_user.post(
        "/api/v1/client/estimate/submit",
        json={
            "rules_version": "v2",
            "service": "vejos_irengimas",
            "method": "sejimas",
            "area_m2": 400,
            "km_one_way": 20,
            "mole_net": False,
            "phone": "+37062222222",
            "address": "Klaipeda, Tiltu g. 1",
        },
    )
    assert resp.status_code == 201
    project_id = resp.json()["project_id"]

    # Admin sets final quote
    fq_resp = await admin_user.post(
        f"/api/v1/admin/ops/project/{project_id}/final-quote",
        json={
            "service": "vejos_irengimas",
            "method": "sejimas",
            "actual_area_m2": 420,
            "final_total_eur": 2100.0,
            "notes": "Prideta papildoma zona",
        },
    )
    assert fq_resp.status_code == 200
    assert fq_resp.json()["ok"] is True

    # Verify project updated
    proj_resp = await admin_user.get(f"/api/v1/projects/{project_id}")
    proj = proj_resp.json()["project"]
    ci = proj["client_info"]
    assert ci["quote_pending"] is False
    assert ci["final_quote"]["final_total_eur"] == 2100.0
    assert ci["final_quote"]["actual_area_m2"] == 420
    assert ci["final_quote"]["notes"] == "Prideta papildoma zona"
    assert proj["total_price_client"] == 2100.0
    assert float(proj["area_m2"]) == 420.0


@pytest.mark.asyncio
async def test_admin_final_quote_not_draft(admin_user):
    # Create project directly as admin (DRAFT)
    create_resp = await admin_user.post(
        "/api/v1/projects",
        json={"client_info": {"name": "Test", "client_id": "fq-test-" + str(uuid.uuid4())[:8]}},
    )
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    # Transition to PAID (need deposit first)
    pid = "MANUAL-FQ-" + str(uuid.uuid4())[:8]
    await admin_user.post(
        f"/api/v1/projects/{project_id}/payments/manual",
        json={
            "payment_type": "DEPOSIT",
            "amount": 100,
            "currency": "EUR",
            "payment_method": "BANK_TRANSFER",
            "provider_event_id": pid,
        },
    )

    # Try final quote on non-DRAFT
    fq_resp = await admin_user.post(
        f"/api/v1/admin/ops/project/{project_id}/final-quote",
        json={
            "service": "vejos_irengimas",
            "method": "sejimas",
            "actual_area_m2": 100,
            "final_total_eur": 500.0,
        },
    )
    assert fq_resp.status_code == 400


@pytest.mark.asyncio
async def test_admin_final_quote_already_set(client_user, admin_user):
    # Create project via estimate
    resp = await client_user.post(
        "/api/v1/client/estimate/submit",
        json={
            "rules_version": "v2",
            "service": "vejos_irengimas",
            "method": "sejimas",
            "area_m2": 200,
            "phone": "+37063333333",
            "address": "Siauliai, Vilniaus g. 1",
        },
    )
    project_id = resp.json()["project_id"]

    # Set final quote
    await admin_user.post(
        f"/api/v1/admin/ops/project/{project_id}/final-quote",
        json={
            "service": "vejos_irengimas",
            "method": "sejimas",
            "actual_area_m2": 200,
            "final_total_eur": 1000.0,
        },
    )

    # Try again — should fail
    fq_resp = await admin_user.post(
        f"/api/v1/admin/ops/project/{project_id}/final-quote",
        json={
            "service": "vejos_irengimas",
            "method": "sejimas",
            "actual_area_m2": 200,
            "final_total_eur": 1200.0,
        },
    )
    assert fq_resp.status_code == 400
