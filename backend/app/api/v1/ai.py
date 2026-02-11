"""AI admin endpoints — parse-intent, view model (V3 Diena 4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.core.dependencies import get_db

router = APIRouter()


# --- AI view (V3 Diena 4) ---


class AiAttentionItem(BaseModel):
    entity_id: str
    scope: str
    confidence: float
    intent: str = ""
    timestamp: str | None = None


class AiViewModel(BaseModel):
    low_confidence_count: int
    attention_items: list[AiAttentionItem]
    ai_summary: str | None = None
    view_version: str


@router.get("/admin/ai/view", response_model=AiViewModel)
def ai_view(
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """V3 view model: low confidence count, attention items, ai_summary."""
    from app.services.admin_read_models import build_ai_view

    settings = get_settings()
    data = build_ai_view(db, settings=settings)

    items = [AiAttentionItem(**i) for i in data["attention_items"]]
    return AiViewModel(
        low_confidence_count=data["low_confidence_count"],
        attention_items=items,
        ai_summary=data.get("ai_summary"),
        view_version=data["view_version"],
    )


def _ensure_ai_intent_enabled() -> None:
    settings = get_settings()
    if not settings.enable_ai_intent:
        raise HTTPException(404, "Nerastas")


class ParseIntentRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    override_provider: str | None = None
    override_model: str | None = None


class ParseIntentResponse(BaseModel):
    intent: str
    confidence: float
    params: dict
    provider: str
    model: str
    attempts: int
    latency_ms: float


@router.post(
    "/admin/ai/parse-intent",
    response_model=ParseIntentResponse,
    summary="Classify caller intent via AI",
)
async def parse_intent_endpoint(
    body: ParseIntentRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("ADMIN")),
):
    _ensure_ai_intent_enabled()

    from app.services.ai.intent.service import parse_intent

    result = await parse_intent(
        body.text,
        db,
        override_provider=body.override_provider,
        override_model=body.override_model,
        actor_id=user.id,
    )
    db.commit()

    return ParseIntentResponse(
        intent=result.intent_result.intent,
        confidence=result.intent_result.confidence,
        params=result.intent_result.params,
        provider=result.provider_result.provider,
        model=result.provider_result.model,
        attempts=result.attempts,
        latency_ms=result.total_latency_ms,
    )
