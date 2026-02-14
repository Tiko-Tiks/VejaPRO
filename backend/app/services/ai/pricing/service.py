"""AI Pricing Scope — generates price proposals with deterministic base + LLM correction.

Architecture:
  1. Deterministic base = midpoint(get_base_range) + compute_addons_total
  2. LLM adjusts within ±max_adjustment_pct via pricing factors
  3. Confidence bucket calculated backend-side (LLM confidence ignored)
  4. Input fingerprint for idempotency (cache invalidation on survey/data change)
  5. Zero PII sent to LLM — only anonymised area/factors/prices

Storage:
  - vision_analysis["ai_pricing"]      — AIPricingResult
  - vision_analysis["ai_pricing_meta"] — {"fingerprint", "generated_at"}
  - client_info["extended_survey"]     — SiteFactors
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.project import Project
from app.services.ai.common import router as ai_router
from app.services.ai.common.audit import log_ai_run
from app.services.estimate_rules import compute_addons_total, get_base_range

from .contracts import (
    AIPricingResult,
    PricingFactor,
    clamp_adjustment,
    compute_confidence_bucket,
    compute_survey_completeness,
    filter_valid_factors,
)

logger = logging.getLogger(__name__)

OBSTACLE_CODES = {
    "TREES",
    "FENCE",
    "UTILITIES",
    "PAVERS",
    "SLOPE_BREAK",
    "DRAINAGE",
    "OTHER_CODED",
}

PRICING_SYSTEM_PROMPT = (
    "Tu esi vejos/sodo projektų kainų analitikas. Tau pateikta bazinė kaina, vietos faktoriai ir panašių projektų kainos.\n"
    "Tavo užduotis: pasiūlyti korekcijos faktorius, kurie koreguoja bazinę kainą.\n\n"
    "TAISYKLĖS:\n"
    "- Grąžink TIK validų JSON, be jokio kito teksto.\n"
    "- Kiekvienas faktorius turi turėti: name, impact_eur, description.\n"
    '- Leistini factor names: "slope_adjustment", "soil_preparation", "vegetation_removal", '
    '"access_difficulty", "distance_surcharge", "obstacle_clearing", "irrigation_bonus", '
    '"seasonal_demand", "complexity_premium".\n'
    "- impact_eur gali būti teigiamas (brangiau) arba neigiamas (pigiau).\n"
    "- reasoning_lt turi būti lietuviškai, 1-3 sakiniai paaiškinant logiką.\n\n"
    'Schema: {"factors": [{"name": "...", "impact_eur": 0.0, "description": "..."}], "reasoning_lt": "..."}'
)


# ---------------------------------------------------------------------------
# Similar projects query + IQR filter
# ---------------------------------------------------------------------------


def _find_similar_projects(
    db: Session,
    area_m2: float,
    complexity: str,
    *,
    exclude_project_id: str | None = None,
) -> list[dict[str, Any]]:
    """Find similar completed projects for pricing reference.

    Filters:
    - status IN ('CERTIFIED', 'ACTIVE')
    - total_price_client IS NOT NULL
    - area within ±30%
    - IQR outlier filter (only when n >= 4)
    - Max 10 results (no PII — only area, price, has_robot, addons keys)
    """
    area_min = area_m2 * 0.7
    area_max = area_m2 * 1.3

    query = db.query(Project).filter(
        and_(
            Project.status.in_(["CERTIFIED", "ACTIVE"]),
            Project.total_price_client.isnot(None),
            Project.area_m2.isnot(None),
            Project.area_m2 >= area_min,
            Project.area_m2 <= area_max,
        )
    )
    if exclude_project_id:
        query = query.filter(Project.id != exclude_project_id)

    candidates = query.order_by(Project.updated_at.desc()).limit(15).all()

    if not candidates:
        return []

    # Extract prices for IQR
    prices = [float(p.total_price_client) for p in candidates]

    # IQR filter only when n >= 4
    if len(prices) >= 4:
        prices_sorted = sorted(prices)
        n = len(prices_sorted)
        q1 = prices_sorted[n // 4]
        q3 = prices_sorted[(3 * n) // 4]
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        filtered = [p for p in candidates if lower <= float(p.total_price_client) <= upper]
    else:
        filtered = candidates

    # Max 10 results, anonymised
    results: list[dict[str, Any]] = []
    for p in filtered[:10]:
        ci = p.client_info or {}
        estimate = ci.get("estimate") or {}
        addons = estimate.get("addons_selected") or []
        addon_keys = [a.get("key") for a in addons if a.get("key")]
        has_robot = any(a.get("key") == "robot" and a.get("variant") not in ("none", None) for a in addons)
        results.append(
            {
                "area_m2": float(p.area_m2) if p.area_m2 else 0,
                "price": float(p.total_price_client),
                "has_robot": has_robot,
                "addon_keys": addon_keys,
            }
        )

    return results


# ---------------------------------------------------------------------------
# Input fingerprint
# ---------------------------------------------------------------------------


def _compute_input_fingerprint(
    area_m2: float,
    survey: dict | None,
    addons: list[dict],
    service_type: str,
    model_version: str,
    similar_ids: list[str],
    max_adjustment_pct: int,
) -> str:
    """Compute SHA256 fingerprint from sorted+normalised input data."""
    payload = {
        "area_m2": round(area_m2, 2),
        "survey": dict(sorted((survey or {}).items())),
        "addons": sorted([json.dumps(a, sort_keys=True) for a in addons]),
        "service_type": service_type,
        "model_version": model_version,
        "similar_ids": sorted(similar_ids),
        "max_adjustment_pct": max_adjustment_pct,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# JSON extraction from LLM response
# ---------------------------------------------------------------------------


def _extract_json(raw: str) -> dict[str, Any] | None:
    """Tolerant JSON extraction: handles fences, trailing text."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(s[start : end + 1])
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Build prompt (zero PII)
# ---------------------------------------------------------------------------


def _build_prompt(
    deterministic_base: float,
    area_m2: float,
    complexity: str,
    survey: dict | None,
    similar_projects: list[dict[str, Any]],
) -> str:
    """Build LLM prompt with zero PII — only area, factors, prices."""
    parts = [
        f"Bazinė kaina (deterministinė): {deterministic_base:.2f} EUR",
        f"Plotas: {area_m2:.1f} m²",
        f"Sudėtingumas: {complexity}",
    ]

    if survey:
        survey_lines = []
        for k, v in sorted(survey.items()):
            if k in ("updated_at", "updated_by"):
                continue
            survey_lines.append(f"  {k}: {v}")
        if survey_lines:
            parts.append("Vietos faktoriai:\n" + "\n".join(survey_lines))

    if similar_projects:
        sp_lines = []
        for i, sp in enumerate(similar_projects, 1):
            sp_lines.append(
                f"  #{i}: plotas={sp['area_m2']:.0f}m², kaina={sp['price']:.2f}EUR, "
                f"robotas={'TAIP' if sp.get('has_robot') else 'NE'}, "
                f"priedai={','.join(sp.get('addon_keys', []))}"
            )
        parts.append(f"Panašūs projektai ({len(similar_projects)}):\n" + "\n".join(sp_lines))
    else:
        parts.append("Panašių projektų nerasta.")

    return "\n\n".join(parts)


def _normalize_survey_for_prompt(survey: dict | None) -> dict[str, Any]:
    if not isinstance(survey, dict):
        return {}
    normalized: dict[str, Any] = {}
    for k, v in survey.items():
        if k in ("updated_at", "updated_by"):
            continue
        if k == "obstacles":
            raw = v if isinstance(v, list) else []
            codes = [str(x).strip().upper() for x in raw if str(x).strip().upper() in OBSTACLE_CODES]
            normalized[k] = sorted(codes)
            continue
        normalized[k] = v
    return normalized


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def generate_pricing_proposal(
    project_id: str,
    db: Session,
) -> AIPricingResult | None:
    """Generate AI pricing proposal for a project.

    Returns AIPricingResult (status="ok" or "fallback"), or None if flag disabled.
    """
    settings = get_settings()
    if not settings.enable_ai_pricing:
        return None

    # Load project
    dialect_name = (getattr(getattr(db, "bind", None), "dialect", None) or type("x", (), {"name": ""})()).name
    if str(dialect_name).lower() == "sqlite":
        project = db.get(Project, project_id)
    else:
        project = db.query(Project).filter(Project.id == project_id).with_for_update().one_or_none()
    if not project:
        logger.warning("AI pricing: project %s not found", project_id)
        return None

    # --- Extract estimate data ---
    ci = project.client_info or {}
    estimate = ci.get("estimate") or {}
    area_m2 = float(project.area_m2 or estimate.get("area_m2") or 0)
    if area_m2 <= 0:
        logger.warning("AI pricing: project %s has no area_m2", project_id)
        return None

    complexity = str(estimate.get("ai_complexity") or "MED").upper()
    if complexity not in ("LOW", "MED", "HIGH"):
        complexity = "MED"
    service_type = str(estimate.get("service_type") or "UNKNOWN").upper()

    addons = estimate.get("addons_selected") or []
    survey = ci.get("extended_survey") or {}
    survey_for_prompt = _normalize_survey_for_prompt(survey)

    # --- Compute deterministic base ---
    base_range = get_base_range(area_m2, complexity)
    base_midpoint = round((base_range["min"] + base_range["max"]) / 2, 2)
    addons_total = compute_addons_total(addons)
    deterministic_base = round(base_midpoint + addons_total, 2)

    max_pct = settings.ai_pricing_max_adjustment_pct

    # --- Similar projects ---
    similar = _find_similar_projects(db, area_m2, complexity, exclude_project_id=project_id)
    similar_ids = [str(s.get("area_m2", 0)) + "_" + str(s.get("price", 0)) for s in similar]

    # --- Input fingerprint ---
    config = ai_router.resolve("pricing")
    model_version = config.model or "unknown"
    fingerprint = _compute_input_fingerprint(
        area_m2,
        survey,
        addons,
        service_type,
        model_version,
        similar_ids,
        max_pct,
    )

    # --- Idempotency check ---
    va = dict(project.vision_analysis or {})
    meta = va.get("ai_pricing_meta") or {}
    if meta.get("fingerprint") == fingerprint and va.get("ai_pricing"):
        cached = va["ai_pricing"]
        return AIPricingResult(**cached)

    # --- Confidence ---
    survey_score = compute_survey_completeness(survey)
    bucket = compute_confidence_bucket(survey_score, len(similar))

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # --- Build prompt ---
    prompt_text = _build_prompt(deterministic_base, area_m2, complexity, survey_for_prompt, similar)

    # --- Call LLM ---
    llm_factors: list[PricingFactor] = []
    reasoning_lt = ""
    status = "ok"

    try:
        provider_result = await config.provider.generate(
            prompt_text,
            system_prompt=PRICING_SYSTEM_PROMPT,
            model=config.model,
            temperature=0.2,
            max_tokens=512,
            timeout_seconds=config.timeout_seconds,
        )

        parsed = _extract_json(provider_result.raw_text)
        if parsed:
            raw_factors = parsed.get("factors") or []
            llm_factors = filter_valid_factors(raw_factors, deterministic_base)
            reasoning_lt = str(parsed.get("reasoning_lt") or "")
        else:
            logger.warning("AI pricing: could not parse JSON from LLM for project %s", project_id)
            status = "fallback"
            reasoning_lt = "AI analizė nepavyko. Rodoma tik deterministinė kaina."

    except Exception:
        logger.warning("AI pricing: provider failed for project %s", project_id, exc_info=True)
        status = "fallback"
        reasoning_lt = "AI analizė nepavyko. Rodoma tik deterministinė kaina."
        provider_result = None

    # --- Compute final prices ---
    if status == "ok" and llm_factors:
        llm_adjustment = clamp_adjustment(llm_factors, deterministic_base, max_pct)
    else:
        llm_adjustment = 0.0
        if status == "ok" and not llm_factors:
            # LLM returned valid JSON but no factors — still "ok" with 0 adjustment
            pass

    recommended_price = round(deterministic_base + llm_adjustment, 2)
    price_range_min = round(base_range["min"] + addons_total + llm_adjustment, 2)
    price_range_max = round(base_range["max"] + addons_total + llm_adjustment, 2)

    result = AIPricingResult(
        status=status,
        deterministic_base=deterministic_base,
        llm_adjustment=llm_adjustment,
        recommended_price=recommended_price,
        price_range_min=price_range_min,
        price_range_max=price_range_max,
        confidence=survey_score,
        confidence_bucket=bucket,
        factors=llm_factors if status == "ok" else [],
        reasoning_lt=reasoning_lt,
        similar_projects_used=len(similar),
        model_version=model_version,
        input_fingerprint=fingerprint,
        generated_at=now_iso,
    )

    # --- Store in JSONB (merge pattern) ---
    va = dict(project.vision_analysis or {})
    va["ai_pricing"] = result.model_dump()
    va["ai_pricing_meta"] = {
        "fingerprint": fingerprint,
        "generated_at": now_iso,
    }
    project.vision_analysis = va
    db.add(project)
    db.flush()

    # --- Audit (success-only for AI run) ---
    if provider_result and status == "ok":
        log_ai_run(
            db,
            scope="pricing",
            provider_result=provider_result,
            prompt_text=prompt_text,
            parsed_output=result.model_dump(),
            extra_meta={
                "project_id": project_id,
                "fingerprint": fingerprint,
                "similar_count": len(similar),
                "confidence_bucket": bucket,
            },
        )

    return result
