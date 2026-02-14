"""Contracts for AI Pricing Scope — data models and validation constants."""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums for extended site survey
# ---------------------------------------------------------------------------


class SoilType(StrEnum):
    SAND = "SAND"
    CLAY = "CLAY"
    LOAM = "LOAM"
    PEAT = "PEAT"
    UNKNOWN = "UNKNOWN"


class SlopeGrade(StrEnum):
    FLAT = "FLAT"
    GENTLE = "GENTLE"
    MODERATE = "MODERATE"
    STEEP = "STEEP"


class ExistingVegetation(StrEnum):
    BARE = "BARE"
    SPARSE_GRASS = "SPARSE_GRASS"
    DENSE_GRASS = "DENSE_GRASS"
    WEEDS = "WEEDS"
    MIXED = "MIXED"


class EquipmentAccess(StrEnum):
    EASY = "EASY"
    RESTRICTED = "RESTRICTED"
    DIFFICULT = "DIFFICULT"


# ---------------------------------------------------------------------------
# Site factors (extended survey)
# ---------------------------------------------------------------------------

ObstacleCode = Literal["TREES", "FENCE", "UTILITIES", "PAVERS", "SLOPE_BREAK", "DRAINAGE", "OTHER_CODED"]


class SiteFactors(BaseModel):
    """Extended site survey filled by admin/expert before AI pricing."""

    soil_type: SoilType = SoilType.UNKNOWN
    slope_grade: SlopeGrade = SlopeGrade.FLAT
    existing_vegetation: ExistingVegetation = ExistingVegetation.BARE
    equipment_access: EquipmentAccess = EquipmentAccess.EASY
    distance_km: float = Field(default=0.0, ge=0, le=500)
    obstacles: list[ObstacleCode] = Field(default_factory=list)
    irrigation_existing: bool = False


# ---------------------------------------------------------------------------
# LLM pricing factors
# ---------------------------------------------------------------------------

ALLOWED_FACTORS: set[str] = {
    "slope_adjustment",
    "soil_preparation",
    "vegetation_removal",
    "access_difficulty",
    "distance_surcharge",
    "obstacle_clearing",
    "irrigation_bonus",
    "seasonal_demand",
    "complexity_premium",
}


class PricingFactor(BaseModel):
    """A single price adjustment factor returned by LLM."""

    name: str
    impact_eur: float
    description: str = ""


# ---------------------------------------------------------------------------
# AI Pricing Result
# ---------------------------------------------------------------------------

SURVEY_FIELDS = [
    "soil_type",
    "slope_grade",
    "existing_vegetation",
    "equipment_access",
    "distance_km",
    "obstacles",
    "irrigation_existing",
]

SURVEY_DEFAULTS: dict[str, object] = {
    "soil_type": "UNKNOWN",
    "slope_grade": "FLAT",
    "existing_vegetation": "BARE",
    "equipment_access": "EASY",
    "distance_km": 0.0,
    "obstacles": [],
    "irrigation_existing": False,
}


class AIPricingResult(BaseModel):
    """Full AI pricing proposal stored in vision_analysis JSONB."""

    status: str = "ok"  # "ok" | "fallback"
    deterministic_base: float
    llm_adjustment: float = 0.0
    recommended_price: float
    price_range_min: float
    price_range_max: float
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_bucket: str = "RED"  # GREEN | YELLOW | RED
    factors: list[PricingFactor] = Field(default_factory=list)
    reasoning_lt: str = ""
    similar_projects_used: int = 0
    model_version: str = ""
    input_fingerprint: str = ""
    generated_at: str = ""

    @field_validator("confidence_bucket")
    @classmethod
    def _valid_bucket(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in {"GREEN", "YELLOW", "RED"}:
            return "RED"
        return v


def filter_valid_factors(raw_factors: list[dict], deterministic_base: float) -> list[PricingFactor]:
    """Filter hallucinated factor names and return valid PricingFactor list.

    Logs a warning for each rejected factor name.
    """
    valid: list[PricingFactor] = []
    for f in raw_factors:
        name = str(f.get("name", "")).strip().lower()
        if name not in ALLOWED_FACTORS:
            logger.warning("AI pricing: rejected hallucinated factor name %r", name)
            continue
        try:
            impact = round(float(f.get("impact_eur", 0)), 2)
        except (ValueError, TypeError):
            impact = 0.0
        desc = str(f.get("description", ""))
        valid.append(PricingFactor(name=name, impact_eur=impact, description=desc))
    return valid


def clamp_adjustment(factors: list[PricingFactor], deterministic_base: float, max_pct: int = 20) -> float:
    """Compute total LLM adjustment, clamped to ±max_pct% of deterministic_base."""
    raw_total = sum(f.impact_eur for f in factors)
    limit = abs(deterministic_base) * max_pct / 100.0
    clamped = max(-limit, min(limit, raw_total))
    return round(clamped, 2)


def compute_survey_completeness(survey: Optional[dict]) -> float:
    """Return 0.0–1.0 ratio of non-default survey fields filled."""
    if not survey:
        return 0.0
    filled = 0
    total = len(SURVEY_FIELDS)
    for field_name in SURVEY_FIELDS:
        val = survey.get(field_name)
        default = SURVEY_DEFAULTS.get(field_name)
        if val is not None and val != default:
            filled += 1
    return round(filled / total, 2) if total else 0.0


def compute_confidence_bucket(survey_score: float, similar_count: int) -> str:
    """Compute confidence bucket based on survey completeness and similar project count.

    GREEN: survey_score >= 0.7 AND similar_count >= 5
    YELLOW: survey_score >= 0.4 OR similar_count >= 2
    RED: else
    """
    if survey_score >= 0.7 and similar_count >= 5:
        return "GREEN"
    if survey_score >= 0.4 or similar_count >= 2:
        return "YELLOW"
    return "RED"
