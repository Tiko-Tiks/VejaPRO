"""Admin customers endpoints — list + profile view models.

Thin router: all business logic lives in admin_read_models service.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.services.admin_read_models import build_customer_list, build_customer_profile

router = APIRouter()


@router.get("/admin/customers")
async def list_customers(
    attention_only: bool = Query(True, description="Show only customers needing attention"),
    limit: int = Query(50, ge=1, le=100),
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """List customers aggregated from projects.

    Default: Inbox Zero — only customers with attention_flags.
    When attention_only=false, last_activity_from defaults to 12 months.
    """
    items = build_customer_list(
        db,
        attention_only=attention_only,
        limit=limit,
    )
    return {
        "items": items,
        "has_more": len(items) >= limit,
    }


@router.get("/admin/customers/{client_key}/profile")
async def get_customer_profile(
    client_key: str,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Full customer profile view model.

    Server builds everything — UI only renders.
    Feature flags included so UI knows which tabs to show.
    """
    settings = get_settings()
    profile = build_customer_profile(db, client_key, settings=settings)
    if profile is None:
        raise HTTPException(status_code=404, detail="Klientas nerastas")
    return profile
