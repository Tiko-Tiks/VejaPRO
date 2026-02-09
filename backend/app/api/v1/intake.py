"""
V2.2 Intake API — Admin intake management + public offer response + activation confirm.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.models.project import CallRequest, ClientConfirmation, Project
from app.schemas.intake import (
    ActivationConfirmResponse,
    IntakeQuestionnaireUpdate,
    IntakeStateResponse,
    OfferResponseRequest,
    OfferResponseResult,
    PrepareOfferRequest,
    PrepareOfferResponse,
    PublicOfferView,
    SendOfferResponse,
)
from app.services.intake_service import (
    Actor,
    IntakeConflictError,
    IntakeError,
    _get_intake_state,
    _questionnaire_value,
    handle_public_offer_response,
    prepare_offer,
    questionnaire_complete,
    send_offer_one_click,
    update_intake_and_maybe_autoprepare,
)
from app.services.transition_service import apply_transition
from app.utils.rate_limit import get_client_ip, get_user_agent

logger = logging.getLogger(__name__)

router = APIRouter()


def _ensure_email_intake_enabled() -> None:
    settings = get_settings()
    if not settings.enable_email_intake:
        raise HTTPException(404, "Nerastas")


def _build_actor(current_user: CurrentUser, request: Request) -> Actor:
    return Actor(
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )


# ─── Admin endpoints ──────────────────────────────────


@router.get(
    "/admin/intake/{call_request_id}/state",
    response_model=IntakeStateResponse,
)
async def get_intake_state(
    call_request_id: str,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _ensure_email_intake_enabled()
    cr = db.get(CallRequest, call_request_id)
    if not cr:
        raise HTTPException(404, "Uzklausos nerastos")

    state = _get_intake_state(cr)
    return IntakeStateResponse(
        call_request_id=str(cr.id),
        questionnaire=state.get("questionnaire") or {},
        workflow=state.get("workflow") or {},
        active_offer=state.get("active_offer") or {},
        offer_history=state.get("offer_history") or [],
        questionnaire_complete=questionnaire_complete(state),
    )


@router.patch(
    "/admin/intake/{call_request_id}/questionnaire",
    response_model=IntakeStateResponse,
)
async def update_questionnaire(
    call_request_id: str,
    payload: IntakeQuestionnaireUpdate,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _ensure_email_intake_enabled()
    cr = db.get(CallRequest, call_request_id)
    if not cr:
        raise HTTPException(404, "Uzklausos nerastos")

    actor = _build_actor(current_user, request)
    patch = {
        k: v
        for k, v in payload.model_dump(exclude={"expected_row_version"}).items()
        if v is not None
    }

    try:
        cr = update_intake_and_maybe_autoprepare(
            db,
            call_request=cr,
            patch=patch,
            actor=actor,
            expected_row_version=payload.expected_row_version,
        )
    except IntakeConflictError as e:
        raise HTTPException(409, "Versijos konfliktas") from e
    except IntakeError as e:
        raise HTTPException(400, str(e)) from e

    state = _get_intake_state(cr)
    return IntakeStateResponse(
        call_request_id=str(cr.id),
        questionnaire=state.get("questionnaire") or {},
        workflow=state.get("workflow") or {},
        active_offer=state.get("active_offer") or {},
        offer_history=state.get("offer_history") or [],
        questionnaire_complete=questionnaire_complete(state),
    )


@router.post(
    "/admin/intake/{call_request_id}/prepare-offer",
    response_model=PrepareOfferResponse,
)
async def admin_prepare_offer(
    call_request_id: str,
    payload: PrepareOfferRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _ensure_email_intake_enabled()
    cr = db.get(CallRequest, call_request_id)
    if not cr:
        raise HTTPException(404, "Uzklausos nerastos")

    actor = _build_actor(current_user, request)

    try:
        cr = prepare_offer(
            db,
            call_request=cr,
            kind=payload.kind,
            actor=actor,
            expected_row_version=payload.expected_row_version,
        )
    except IntakeConflictError as e:
        raise HTTPException(409, "Versijos konfliktas") from e
    except IntakeError as e:
        raise HTTPException(400, str(e)) from e

    state = _get_intake_state(cr)
    ao = state.get("active_offer") or {}
    slot = ao.get("slot") or {}

    return PrepareOfferResponse(
        call_request_id=str(cr.id),
        slot_start=slot.get("start"),
        slot_end=slot.get("end"),
        resource_id=slot.get("resource_id"),
        kind=ao.get("kind", "INSPECTION"),
        phase=(state.get("workflow") or {}).get("phase"),
    )


@router.post(
    "/admin/intake/{call_request_id}/send-offer",
    response_model=SendOfferResponse,
    status_code=201,
)
async def admin_send_offer(
    call_request_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _ensure_email_intake_enabled()
    cr = db.get(CallRequest, call_request_id)
    if not cr:
        raise HTTPException(404, "Uzklausos nerastos")

    actor = _build_actor(current_user, request)

    try:
        cr = send_offer_one_click(db, call_request=cr, actor=actor)
    except IntakeConflictError as e:
        raise HTTPException(409, "Versijos konfliktas") from e
    except IntakeError as e:
        raise HTTPException(400, str(e)) from e

    state = _get_intake_state(cr)
    ao = state.get("active_offer") or {}

    return SendOfferResponse(
        call_request_id=str(cr.id),
        appointment_id=ao.get("appointment_id", ""),
        hold_expires_at=ao.get("hold_expires_at", ""),
        attempt_no=int(ao.get("attempt_no") or 0),
        phase=(state.get("workflow") or {}).get("phase", ""),
    )


# ─── Public endpoints ─────────────────────────────────


def _find_call_request_by_offer_token(db: Session, token: str) -> Optional[CallRequest]:
    """Find a CallRequest whose intake_state.active_offer.token_hash matches."""
    from sqlalchemy import select

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    # For Postgres: use JSONB query
    settings = get_settings()
    if not (settings.database_url or "").startswith("sqlite"):
        from sqlalchemy import text

        stmt = text(
            "SELECT id FROM call_requests WHERE intake_state->'active_offer'->>'token_hash' = :hash LIMIT 1"
        )
        row = db.execute(stmt, {"hash": token_hash}).first()
        if row:
            return db.get(CallRequest, row[0])
        return None

    # SQLite fallback: scan (OK for tests, not for prod)
    rows = db.execute(select(CallRequest)).scalars().all()
    for cr in rows:
        state = cr.intake_state or {}
        ao = state.get("active_offer") or {}
        if ao.get("token_hash") == token_hash:
            return cr
    return None


@router.get("/public/offer/{token}", response_model=PublicOfferView)
async def public_offer_view(
    token: str,
    db: Session = Depends(get_db),
):
    cr = _find_call_request_by_offer_token(db, token)
    if not cr:
        raise HTTPException(404, "Pasiulymas nerastas")

    state = _get_intake_state(cr)
    ao = state.get("active_offer") or {}
    slot = ao.get("slot") or {}
    address = _questionnaire_value(state, "address") or ""

    return PublicOfferView(
        slot_start=slot.get("start"),
        slot_end=slot.get("end"),
        address=address,
        kind=ao.get("kind", "INSPECTION"),
        status=ao.get("state", "UNKNOWN"),
    )


@router.post("/public/offer/{token}/respond", response_model=OfferResponseResult)
async def public_offer_respond(
    token: str,
    payload: OfferResponseRequest,
    db: Session = Depends(get_db),
):
    cr = _find_call_request_by_offer_token(db, token)
    if not cr:
        raise HTTPException(404, "Pasiulymas nerastas")

    try:
        cr = handle_public_offer_response(
            db,
            call_request=cr,
            token=token,
            action=payload.action,
            suggest_text=payload.suggest_text,
        )
    except IntakeError as e:
        raise HTTPException(400, str(e)) from e

    state = _get_intake_state(cr)
    ao = state.get("active_offer") or {}
    slot = ao.get("slot") or {}

    if payload.action == "accept":
        return OfferResponseResult(
            status="ACCEPTED",
            message="Apziuros laikas patvirtintas.",
        )

    return OfferResponseResult(
        status="REJECTED",
        message="Pasiulymas atmestas. Naujas laikas paruostas.",
        next_slot_start=slot.get("start"),
        next_slot_end=slot.get("end"),
    )


# ─── Activation confirm (CERTIFIED → ACTIVE via email) ───


@router.post(
    "/public/activations/{token}/confirm",
    response_model=ActivationConfirmResponse,
)
async def activation_confirm(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    confirmation = (
        db.query(ClientConfirmation)
        .filter(ClientConfirmation.token_hash == token_hash)
        .one_or_none()
    )
    if not confirmation:
        raise HTTPException(404, "Patvirtinimas nerastas")

    if confirmation.status != "PENDING":
        raise HTTPException(400, "Patvirtinimas jau panaudotas")

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    if confirmation.expires_at and confirmation.expires_at < now:
        raise HTTPException(400, "Patvirtinimo galiojimas pasibaiges")

    project = db.get(Project, confirmation.project_id)
    if not project:
        raise HTTPException(404, "Projektas nerastas")

    if project.status != "CERTIFIED":
        raise HTTPException(
            400, f"Projektas nera CERTIFIED busenoje (dabartine: {project.status})"
        )

    try:
        from app.schemas.project import ProjectStatus

        apply_transition(
            db,
            project=project,
            new_status=ProjectStatus.ACTIVE,
            actor_type="SYSTEM_EMAIL",
            actor_id=None,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            metadata={
                "channel": confirmation.channel,
                "confirmation_id": str(confirmation.id),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Aktyvavimo klaida: {e}") from e

    confirmation.status = "CONFIRMED"
    confirmation.confirmed_at = now
    db.commit()

    return ActivationConfirmResponse(
        project_id=str(project.id),
        new_status="ACTIVE",
        message="Projektas sekmingai aktyvuotas.",
    )
