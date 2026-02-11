"""Client UI V3 — estimate pricing rules (server-side only)."""

from __future__ import annotations

CURRENT_RULES_VERSION = "v1"

# Base EUR per m² by complexity (min, max)
BASE_RATES = {
    "LOW": {"min_per_m2": 8.0, "max_per_m2": 12.0},
    "MED": {"min_per_m2": 12.0, "max_per_m2": 18.0},
    "HIGH": {"min_per_m2": 18.0, "max_per_m2": 28.0},
}

ADDONS = [
    {
        "key": "seed",
        "label": "Sėkla",
        "variants": [
            {"key": "standard", "label": "Standard", "price": 0.0, "scope": "Įeina į bazę", "recommended": False},
            {"key": "premium", "label": "Premium", "price": 89.0, "scope": "Geresnė kokybė", "recommended": True},
        ],
    },
    {
        "key": "watering",
        "label": "Laistymas",
        "variants": [
            {"key": "none", "label": "Nėra", "price": 0.0, "scope": None, "recommended": False},
            {"key": "basic", "label": "Basic", "price": 199.0, "scope": "Paprastas laistymas", "recommended": False},
            {"key": "smart", "label": "Smart", "price": 449.0, "scope": "Automatinis", "recommended": True},
        ],
    },
    {
        "key": "robot",
        "label": "Robotas",
        "variants": [
            {"key": "none", "label": "Nėra", "price": 0.0, "scope": None, "recommended": False},
            {
                "key": "recommended",
                "label": "Rekomenduojama",
                "price": 0.0,
                "scope": "Kaina po įvertinimo",
                "recommended": True,
            },
        ],
    },
    {
        "key": "maintenance",
        "label": "Priežiūra",
        "variants": [
            {"key": "none", "label": "Nėra", "price": 0.0, "scope": None, "recommended": False},
            {"key": "seasonal", "label": "Sezoninė", "price": 149.0, "scope": "Sezono priežiūra", "recommended": False},
            {"key": "full", "label": "Pilna", "price": 299.0, "scope": "Abonementas po ACTIVE", "recommended": True},
        ],
    },
    {
        "key": "fertilizer",
        "label": "Tręšos",
        "variants": [
            {"key": "none", "label": "Nėra", "price": 0.0, "scope": None, "recommended": False},
            {"key": "starter", "label": "Starter", "price": 49.0, "scope": "Startinis tręšimas", "recommended": False},
            {"key": "season", "label": "Sezonui", "price": 99.0, "scope": "Sezoninis", "recommended": True},
        ],
    },
]

DISCLAIMER = "Galutinę sąmatą patvirtins ekspertas po apžiūros."
CONFIDENCE_MESSAGES = {
    "GREEN": "Aukštas pasitikėjimas.",
    "YELLOW": "Vidutinis pasitikėjimas. Ekspertas patikslinas.",
    "RED": "Žemas pasitikėjimas. Būtina eksperto apžiūra.",
}


def get_base_range(area_m2: float, complexity: str) -> dict[str, float]:
    rates = BASE_RATES.get(complexity, BASE_RATES["MED"])
    return {
        "min": round(area_m2 * rates["min_per_m2"], 2),
        "max": round(area_m2 * rates["max_per_m2"], 2),
    }


def get_addon_price(addon_key: str, variant_key: str) -> float:
    for addon in ADDONS:
        if addon["key"] == addon_key:
            for v in addon["variants"]:
                if v["key"] == variant_key:
                    return float(v["price"])
    return 0.0


def compute_addons_total(addons_selected: list[dict]) -> float:
    total = 0.0
    for sel in addons_selected:
        key = sel.get("key") or sel.get("addon_key")
        variant = sel.get("variant") or sel.get("variant_key")
        if key and variant:
            total += get_addon_price(key, variant)
    return round(total, 2)


def compute_total_range(base_range: dict[str, float], addons_total: float) -> dict[str, float]:
    return {
        "min": round(base_range.get("min", 0) + addons_total, 2),
        "max": round(base_range.get("max", 0) + addons_total, 2),
    }
