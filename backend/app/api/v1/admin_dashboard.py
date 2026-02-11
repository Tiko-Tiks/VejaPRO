"""Admin dashboard endpoints — hero, triage, AI summary, SSE.

Thin router: view model built by admin_read_models.build_dashboard_view.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.core.dependencies import SessionLocal, get_db
from app.services.admin_read_models import build_dashboard_view

router = APIRouter()

_dashboard_sse_connections = 0


@router.get("/admin/dashboard")
async def get_dashboard(
    triage_limit: int = Query(20, ge=1, le=50),
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Dashboard view model: hero stats, triage cards, optional AI summary."""
    settings = get_settings()
    return build_dashboard_view(db, settings=settings, triage_limit=triage_limit)


@router.get("/admin/dashboard/sse")
async def dashboard_sse(
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
):
    """SSE stream for triage updates. Polls every 5s, sends triage items."""
    global _dashboard_sse_connections

    settings = get_settings()
    if _dashboard_sse_connections >= settings.dashboard_sse_max_connections:
        raise HTTPException(429, "Per daug aktyvių SSE jungčių")

    _dashboard_sse_connections += 1

    async def event_stream():
        global _dashboard_sse_connections
        prev_new_calls: int | None = None
        try:
            while True:
                if await request.is_disconnected():
                    break
                db = SessionLocal()
                try:
                    data = build_dashboard_view(db, settings=settings, triage_limit=20)
                    stats = data.get("hero", {}).get("stats", {}) or {}
                    new_calls = stats.get("new_calls", 0)

                    payload = {"type": "triage_update", "triage": data.get("triage", []), "stats": stats}
                    yield f"data: {json.dumps(payload)}\n\n"

                    if prev_new_calls is not None and new_calls > prev_new_calls:
                        event_payload = {"type": "call_request_created", "new_count": new_calls}
                        yield f"data: {json.dumps(event_payload)}\n\n"
                    prev_new_calls = new_calls
                finally:
                    db.close()
                await asyncio.sleep(5)
        finally:
            _dashboard_sse_connections -= 1

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
