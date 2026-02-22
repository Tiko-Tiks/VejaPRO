"""Client UI V3 — estimate pricing rules v2 (deterministic, no AI)."""

from __future__ import annotations

CURRENT_RULES_VERSION = "v2"

# Service -> method -> area tiers (max_area_m2, eur_per_m2)
SERVICES: dict[str, dict] = {
    "vejos_irengimas": {
        "label": "Vejos irengimas",
        "methods": {
            "sejimas": {
                "label": "Sejimas",
                "tiers": [
                    {"max_area": 200, "rate": 5.00},
                    {"max_area": 400, "rate": 4.50},
                    {"max_area": 800, "rate": 4.00},
                    {"max_area": None, "rate": 3.50},
                ],
            },
            "ritinine": {
                "label": "Ritinine veja",
                "tiers": [
                    {"max_area": 200, "rate": 9.00},
                    {"max_area": 400, "rate": 8.00},
                    {"max_area": 800, "rate": 7.00},
                    {"max_area": None, "rate": 6.50},
                ],
            },
            "hidroseija": {
                "label": "Hidroseija",
                "tiers": [
                    {"max_area": 200, "rate": 4.00},
                    {"max_area": 400, "rate": 3.50},
                    {"max_area": 800, "rate": 3.00},
                    {"max_area": None, "rate": 2.80},
                ],
            },
        },
    },
    "apleisto_sklypo_tvarkymas": {
        "label": "Apleisto sklypo tvarkymas",
        "methods": {
            "mazas": {
                "label": "Mazas (<20cm)",
                "tiers": [
                    {"max_area": 200, "rate": 3.00},
                    {"max_area": 400, "rate": 2.50},
                    {"max_area": 800, "rate": 2.20},
                    {"max_area": None, "rate": 2.00},
                ],
            },
            "vidutinis": {
                "label": "Vidutinis (20-50cm)",
                "tiers": [
                    {"max_area": 200, "rate": 4.00},
                    {"max_area": 400, "rate": 3.50},
                    {"max_area": 800, "rate": 3.00},
                    {"max_area": None, "rate": 2.80},
                ],
            },
            "didelis": {
                "label": "Didelis (>50cm)",
                "tiers": [
                    {"max_area": 200, "rate": 6.00},
                    {"max_area": 400, "rate": 5.00},
                    {"max_area": 800, "rate": 4.50},
                    {"max_area": None, "rate": 4.00},
                ],
            },
        },
    },
}

ADDONS = {
    "mole_net": {"label": "Kurmiu tinklas", "rate_per_m2": 1.50},
}

TRANSPORT = {"min_eur": 50.0, "rate_per_km": 1.50}

DISCLAIMER = "Kainos yra orientacines ir gali keistis po eksperto apziuros."


# ─── Legacy compatibility (used by AI pricing service) ───────────────────

_LEGACY_BASE_RATES = {
    "LOW": {"min_per_m2": 8.0, "max_per_m2": 12.0},
    "MED": {"min_per_m2": 12.0, "max_per_m2": 18.0},
    "HIGH": {"min_per_m2": 18.0, "max_per_m2": 28.0},
}


def get_base_range(area_m2: float, complexity: str) -> dict[str, float]:
    """Legacy V1: base price range by area and complexity."""
    rates = _LEGACY_BASE_RATES.get(complexity, _LEGACY_BASE_RATES["MED"])
    return {
        "min": round(area_m2 * rates["min_per_m2"], 2),
        "max": round(area_m2 * rates["max_per_m2"], 2),
    }


def compute_addons_total(addons_selected: list[dict]) -> float:
    """Legacy V1: compute addons total (returns 0 for V2 — no variant addons)."""
    return 0.0


# ─── V2 pricing ──────────────────────────────────────────────────────────


def get_rules() -> dict:
    """Return full pricing rules for frontend consumption."""
    services_out = {}
    for svc_key, svc in SERVICES.items():
        methods_out = {}
        for m_key, m in svc["methods"].items():
            methods_out[m_key] = {"label": m["label"], "tiers": m["tiers"]}
        services_out[svc_key] = {"label": svc["label"], "methods": methods_out}

    addons_out = []
    for addon_key, addon in ADDONS.items():
        addons_out.append(
            {
                "key": addon_key,
                "label": addon["label"],
                "rate_per_m2": addon["rate_per_m2"],
                "pricing_mode": "included_in_estimate",
            }
        )

    return {
        "rules_version": CURRENT_RULES_VERSION,
        "services": services_out,
        "addons": addons_out,
        "transport": TRANSPORT,
        "disclaimer": DISCLAIMER,
    }


def get_valid_addon_keys() -> list[str]:
    """Return list of addon keys allowed in addons_selected (for server-side validation)."""
    return list(ADDONS.keys())


def get_rate(service: str, method: str, area_m2: float) -> float:
    """Return EUR/m2 rate for given service+method+area."""
    svc = SERVICES.get(service)
    if not svc:
        raise ValueError(f"Unknown service: {service}")
    m = svc["methods"].get(method)
    if not m:
        raise ValueError(f"Unknown method: {method}")
    for tier in m["tiers"]:
        if tier["max_area"] is None or area_m2 <= tier["max_area"]:
            return float(tier["rate"])
    return float(m["tiers"][-1]["rate"])


def compute_price(
    service: str,
    method: str,
    area_m2: float,
    km_one_way: float = 0,
    mole_net: bool = False,
) -> dict:
    """Compute full price breakdown."""
    rate = get_rate(service, method, area_m2)
    base = round(area_m2 * rate, 2)

    transport = round(max(TRANSPORT["min_eur"], km_one_way * TRANSPORT["rate_per_km"]), 2)

    mole_net_total = round(area_m2 * ADDONS["mole_net"]["rate_per_m2"], 2) if mole_net else 0.0

    total = round(base + transport + mole_net_total, 2)

    breakdown = [
        {"label": "Bazine kaina", "amount": base, "detail": f"{area_m2} m2 x {rate} EUR/m2"},
        {"label": "Transportas", "amount": transport, "detail": f"{km_one_way} km"},
    ]
    if mole_net:
        breakdown.append(
            {
                "label": "Kurmiu tinklas",
                "amount": mole_net_total,
                "detail": f"{area_m2} m2 x {ADDONS['mole_net']['rate_per_m2']} EUR/m2",
            }
        )

    return {
        "base_eur": base,
        "rate_eur_m2": rate,
        "transport_eur": transport,
        "mole_net_eur": mole_net_total,
        "total_eur": total,
        "breakdown": breakdown,
        "rules_version": CURRENT_RULES_VERSION,
    }
