"""Admin customers endpoints — list + profile view models.

Thin router: all business logic lives in admin_read_models service.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.services.admin_read_models import (
    build_customer_list,
    build_customer_profile,
    count_unique_clients_12m,
)

router = APIRouter()


@router.get("/admin/customers")
async def list_customers(
    attention_only: bool = Query(True, description="Show only customers needing attention"),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None),
    as_of: datetime | None = Query(None),
    attention: str | None = Query(None, description="Filter by attention flag"),
    project_status: str | None = Query(None, description="Filter by latest project status"),
    financial_state: str | None = Query(None, description="Filter by financial state"),
    last_activity_from: datetime | None = Query(None),
    last_activity_to: datetime | None = Query(None),
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """List customers aggregated from projects.

    Default: Inbox Zero — only customers with attention_flags.
    When attention_only=false, last_activity_from defaults to 12 months.
    """
    if not attention_only and limit > 100:
        raise HTTPException(status_code=400, detail="limit max 100 kai attention_only=false")
    try:
        return build_customer_list(
            db,
            attention_only=attention_only,
            limit=limit,
            cursor=cursor,
            as_of=as_of,
            attention=attention,
            project_status=project_status,
            financial_state=financial_state,
            last_activity_from=last_activity_from,
            last_activity_to=last_activity_to,
        )
    except ValueError as exc:
        msg = str(exc) or "Neteisingi parametrai"
        raise HTTPException(status_code=400, detail=msg) from exc


@router.get("/admin/customers/stats")
async def customers_stats(
    as_of: datetime | None = Query(None),
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Dashboard helper: count unique derived clients in last 12 months."""
    return count_unique_clients_12m(db, as_of=as_of)


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
