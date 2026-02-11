"""Admin global search — projects, call requests. LOCK 1.4: no PII in logs, 404 on not found."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.core.dependencies import get_db
from app.models.project import CallRequest, Project

router = APIRouter()
logger = logging.getLogger(__name__)


class SearchItemOut(BaseModel):
    type: str
    id: str
    label: str
    href: str


class SearchResponseOut(BaseModel):
    items: list[SearchItemOut]


def _mask_id(s: str, visible: int = 8) -> str:
    """Show first N chars for display (no PII)."""
    if not s or len(s) < visible:
        return s or ""
    return s[:visible] + "…"


@router.get("/admin/search", response_model=SearchResponseOut)
def admin_search(
    q: str = Query(..., min_length=1, max_length=128),
    limit: int = Query(50, ge=1, le=50),
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Global search: projects, call requests. LOCK 1.4: log only q length, 404 on no access."""
    if current_user.role != "ADMIN":
        raise HTTPException(403, "Prieiga uždrausta")

    # LOCK 1.4: no PII in logs — log only length + request_id
    req_id = getattr(request, "state", {}).get("request_id", "-") if request else "-"
    logger.info("admin_search q_len=%d request_id=%s", len(q), req_id)

    q_clean = q.strip()
    if not q_clean:
        return SearchResponseOut(items=[])

    items: list[SearchItemOut] = []

    # Projects: by ID prefix or status
    try:
        if len(q_clean) >= 4:
            proj_q = db.query(Project).filter(
                or_(
                    cast(Project.id, String).like(f"{q_clean}%"),
                    Project.status.ilike(f"%{q_clean}%"),
                )
            ).limit(limit)
            for p in proj_q.all():
                items.append(
                    SearchItemOut(
                        type="project",
                        id=str(p.id),
                        label=f"Projektas {_mask_id(str(p.id))} ({p.status})",
                        href=f"/admin/projects#{p.id}",
                    )
                )
    except Exception as exc:
        logger.warning("admin_search projects error: %s", exc, exc_info=True)

    # Call requests: by ID
    try:
        if len(q_clean) >= 4:
            call_q = db.query(CallRequest).filter(
                cast(CallRequest.id, String).like(f"{q_clean}%")
            ).limit(limit - len(items))
            for c in call_q.all():
                items.append(
                    SearchItemOut(
                        type="call_request",
                        id=str(c.id),
                        label=f"Skambučio užklausa {_mask_id(str(c.id))}",
                        href="/admin/calls",
                    )
                )
    except Exception as exc:
        logger.warning("admin_search calls error: %s", exc, exc_info=True)

    # Dedupe by id+type and limit
    seen = set()
    unique = []
    for it in items:
        key = (it.type, it.id)
        if key not in seen:
            seen.add(key)
            unique.append(it)
        if len(unique) >= limit:
            break

    return SearchResponseOut(items=unique[:limit])
