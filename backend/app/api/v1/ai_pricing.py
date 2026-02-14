"""AI Pricing API — admin-only endpoints for AI price proposals.

Endpoints:
  POST /admin/ops/pricing/{project_id}/generate — generate AI pricing proposal
  POST /admin/ops/pricing/{project_id}/decide   — approve / edit / ignore proposal
  PUT  /admin/ops/pricing/{project_id}/survey    — save extended site survey
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.models.project import Project
from app.services.ai.pricing.contracts import SiteFactors
from app.services.ai.pricing.service import generate_pricing_proposal
from app.services.transition_service import create_audit_log

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Feature flag guard
# ---------------------------------------------------------------------------


def _ensure_ai_pricing_enabled() -> None:
    settings = get_settings()
    if not settings.enable_ai_pricing:
        raise HTTPException(status_code=404, detail="Nerastas")


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class GenerateResponse(BaseModel):
    status: str  # "ok" | "fallback"
    ai_pricing: dict


class DecideRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|edit|ignore)$")
    proposal_fingerprint: str
    adjusted_price: Optional[float] = Field(default=None, gt=0)
    reason: Optional[str] = None


class SurveyRequest(BaseModel):
    """Extended site survey — validated via SiteFactors."""

    soil_type: Optional[str] = None
    slope_grade: Optional[str] = None
    existing_vegetation: Optional[str] = None
    equipment_access: Optional[str] = None
    distance_km: Optional[float] = None
    obstacles: Optional[list[str]] = None
    irrigation_existing: Optional[bool] = None


# ---------------------------------------------------------------------------
# POST /admin/ops/pricing/{project_id}/generate
# ---------------------------------------------------------------------------


@router.post(
    "/admin/ops/pricing/{project_id}/generate",
    response_model=GenerateResponse,
    dependencies=[Depends(_ensure_ai_pricing_enabled)],
)
async def generate_pricing(
    project_id: str,
    user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Generate AI pricing proposal for a project."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projektas nerastas")

    result = await generate_pricing_proposal(project_id, db)
    if result is None:
        raise HTTPException(status_code=404, detail="Nerastas")

    db.commit()

    return GenerateResponse(
        status=result.status,
        ai_pricing=result.model_dump(),
    )


# ---------------------------------------------------------------------------
# POST /admin/ops/pricing/{project_id}/decide
# ---------------------------------------------------------------------------


@router.post(
    "/admin/ops/pricing/{project_id}/decide",
    dependencies=[Depends(_ensure_ai_pricing_enabled)],
)
async def decide_pricing(
    project_id: str,
    body: DecideRequest,
    user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Record admin decision on AI pricing proposal: approve / edit / ignore."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projektas nerastas")

    va = dict(project.vision_analysis or {})
    ai_pricing = va.get("ai_pricing")
    meta = va.get("ai_pricing_meta") or {}

    if not ai_pricing:
        raise HTTPException(status_code=404, detail="AI pasiūlymas nerastas")

    # --- Stale proposal check ---
    current_fingerprint = meta.get("fingerprint", "")
    if body.proposal_fingerprint != current_fingerprint:
        raise HTTPException(status_code=409, detail="Pasiūlymas pasikeitė")

    action = body.action.lower()
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if action == "approve":
        # Cannot approve a fallback proposal
        if ai_pricing.get("status") == "fallback":
            raise HTTPException(status_code=422, detail="Negalima patvirtinti fallback pasiūlymo")

        recommended = ai_pricing.get("recommended_price")
        if recommended is None:
            raise HTTPException(status_code=422, detail="AI pasiūlyme nėra rekomenduojamos kainos")

        project.total_price_client = round(float(recommended), 2)
        audit_action = "AI_PRICING_DECISION_APPROVED"

    elif action == "edit":
        if body.adjusted_price is None:
            raise HTTPException(status_code=422, detail="Būtina nurodyti adjusted_price")
        if not body.reason or len(body.reason.strip()) < 8:
            raise HTTPException(status_code=422, detail="Priežastis turi būti bent 8 simbolių")

        project.total_price_client = round(body.adjusted_price, 2)
        audit_action = "AI_PRICING_DECISION_EDITED"

    elif action == "ignore":
        audit_action = "AI_PRICING_DECISION_IGNORED"

    else:
        raise HTTPException(status_code=422, detail="Nežinomas veiksmas")

    # Save decision
    decision = {
        "action": action,
        "decided_by": user.id,
        "decided_at": now_iso,
        "proposal_fingerprint": body.proposal_fingerprint,
    }
    if action == "edit":
        decision["adjusted_price"] = round(body.adjusted_price, 2)
        decision["reason"] = body.reason.strip()

    va["ai_pricing_decision"] = decision
    project.vision_analysis = va
    db.add(project)

    # Audit
    create_audit_log(
        db,
        entity_type="project",
        entity_id=project_id,
        action=audit_action,
        old_value=None,
        new_value=decision,
        actor_type="ADMIN",
        actor_id=user.id,
        ip_address=None,
        user_agent=None,
        metadata={"proposal_fingerprint": body.proposal_fingerprint},
    )

    db.commit()

    return {"ok": True, "action": action}


# ---------------------------------------------------------------------------
# PUT /admin/ops/pricing/{project_id}/survey
# ---------------------------------------------------------------------------


@router.put(
    "/admin/ops/pricing/{project_id}/survey",
    dependencies=[Depends(_ensure_ai_pricing_enabled)],
)
async def save_survey(
    project_id: str,
    body: SurveyRequest,
    user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Save extended site survey for a project (used by AI pricing)."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projektas nerastas")

    # Validate via SiteFactors (will raise 422 on invalid enums)
    survey_data = body.model_dump(exclude_none=True)
    SiteFactors(**survey_data)

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    survey_data["updated_at"] = now_iso
    survey_data["updated_by"] = user.id

    # Merge into client_info (don't overwrite)
    ci = dict(project.client_info or {})
    ci["extended_survey"] = survey_data
    project.client_info = ci
    db.add(project)
    db.commit()

    return {"ok": True, "extended_survey": survey_data}
