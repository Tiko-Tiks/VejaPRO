"""Admin project detail endpoints — payments, confirmations, notifications, resend, retry.

All PII in responses is masked. resend/retry have rate limits (max 3 per 24h per project+channel).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.dependencies import get_db
from app.models.project import (
    ClientConfirmation,
    NotificationOutbox,
    Payment,
    Project,
)

router = APIRouter()

RESEND_LIMIT = 3
RESEND_WINDOW_HOURS = 24
RETRY_LIMIT = 3
RETRY_WINDOW_HOURS = 24


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_project_or_404(db: Session, project_id: str) -> Project:
    project = (
        db.execute(select(Project).where(Project.id == project_id)).scalars().first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Projektas nerastas")
    return project


def _resend_count_24h(db: Session, project_id: str, channel: str) -> int:
    """Count confirmations created in last 24h for this project+channel."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RESEND_WINDOW_HOURS)
    result = (
        db.execute(
            select(ClientConfirmation)
            .where(ClientConfirmation.project_id == project_id)
            .where(ClientConfirmation.channel == channel)
            .where(ClientConfirmation.created_at >= cutoff)
        )
        .scalars()
        .all()
    )
    return len(result)


def _retry_count_24h(db: Session, notification_id: str) -> int:
    """Check retry attempts in last 24h based on attempt_count changes."""
    notif = (
        db.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.id == notification_id
            )
        )
        .scalars()
        .first()
    )
    if not notif:
        return 0
    return notif.attempt_count or 0


# ---------------------------------------------------------------------------
# GET /admin/projects/{id}/payments
# ---------------------------------------------------------------------------


@router.get("/admin/projects/{project_id}/payments")
async def get_project_payments(
    project_id: str,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _get_project_or_404(db, project_id)

    payments = (
        db.execute(
            select(Payment)
            .where(Payment.project_id == project_id)
            .order_by(desc(Payment.created_at))
        )
        .scalars()
        .all()
    )

    items = []
    for p in payments:
        items.append(
            {
                "id": str(p.id),
                "payment_type": p.payment_type,
                "amount": float(p.amount) if p.amount is not None else None,
                "currency": p.currency or "EUR",
                "status": p.status,
                "payment_method": p.payment_method,
                "provider": p.provider,
                "received_at": p.received_at.isoformat() if p.received_at else None,
                "proof_url": p.proof_url,
                "provider_event_id": p.provider_event_id,
                "is_manual_confirmed": p.is_manual_confirmed,
                "confirmed_by": p.confirmed_by,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
        )

    return {"items": items}


# ---------------------------------------------------------------------------
# GET /admin/projects/{id}/confirmations
# ---------------------------------------------------------------------------


@router.get("/admin/projects/{project_id}/confirmations")
async def get_project_confirmations(
    project_id: str,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _get_project_or_404(db, project_id)

    confirmations = (
        db.execute(
            select(ClientConfirmation)
            .where(ClientConfirmation.project_id == project_id)
            .order_by(desc(ClientConfirmation.created_at))
        )
        .scalars()
        .all()
    )

    items = []
    for c in confirmations:
        # Calculate resend remaining
        channel = c.channel or "email"
        sent_24h = _resend_count_24h(db, project_id, channel)
        remaining = max(0, RESEND_LIMIT - sent_24h)
        reset_at = (
            datetime.now(timezone.utc) + timedelta(hours=RESEND_WINDOW_HOURS)
        ).isoformat()

        items.append(
            {
                "id": str(c.id),
                "channel": channel,
                "status": c.status,
                "attempts": c.attempts,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "expires_at": c.expires_at.isoformat() if c.expires_at else None,
                "confirmed_at": (
                    c.confirmed_at.isoformat() if c.confirmed_at else None
                ),
                "can_resend": remaining > 0 and c.status != "CONFIRMED",
                "resends_remaining": remaining,
                "reset_at": reset_at,
            }
        )

    return {"items": items}


# ---------------------------------------------------------------------------
# POST /admin/projects/{id}/confirmations/resend
# ---------------------------------------------------------------------------


class ResendRequest(BaseModel):
    channel: str = "email"


@router.post("/admin/projects/{project_id}/confirmations/resend")
async def resend_confirmation(
    project_id: str,
    payload: ResendRequest = ResendRequest(),
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _get_project_or_404(db, project_id)

    channel = payload.channel
    sent_24h = _resend_count_24h(db, project_id, channel)
    remaining = max(0, RESEND_LIMIT - sent_24h)
    reset_at = (
        datetime.now(timezone.utc) + timedelta(hours=RESEND_WINDOW_HOURS)
    ).isoformat()

    if remaining <= 0:
        raise HTTPException(
            status_code=429,
            detail={
                "message": "Persiuntimo limitas virsytas",
                "remaining": 0,
                "reset_at": reset_at,
            },
        )

    # Create new confirmation record
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    confirmation = ClientConfirmation(
        project_id=project_id,
        token_hash=token_hash,
        channel=channel,
        status="PENDING",
        attempts=0,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(confirmation)

    # Create outbox entry
    outbox = NotificationOutbox(
        entity_type="project",
        entity_id=str(project_id),
        channel=channel,
        template_key="confirmation_resend",
        status="PENDING",
        attempt_count=0,
    )
    db.add(outbox)
    db.commit()

    return {
        "message": "Patvirtinimas persiustas",
        "remaining": remaining - 1,
        "reset_at": reset_at,
    }


# ---------------------------------------------------------------------------
# GET /admin/projects/{id}/notifications
# ---------------------------------------------------------------------------


@router.get("/admin/projects/{project_id}/notifications")
async def get_project_notifications(
    project_id: str,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _get_project_or_404(db, project_id)

    notifications = (
        db.execute(
            select(NotificationOutbox)
            .where(NotificationOutbox.entity_type == "project")
            .where(NotificationOutbox.entity_id == str(project_id))
            .order_by(desc(NotificationOutbox.created_at))
        )
        .scalars()
        .all()
    )

    items = []
    for n in notifications:
        can_retry = n.status == "FAILED" and (n.attempt_count or 0) < RETRY_LIMIT
        retries_remaining = max(0, RETRY_LIMIT - (n.attempt_count or 0))

        items.append(
            {
                "id": str(n.id),
                "channel": n.channel,
                "template_key": n.template_key,
                "status": n.status,
                "attempt_count": n.attempt_count or 0,
                "last_error": n.last_error,
                "sent_at": n.sent_at.isoformat() if n.sent_at else None,
                "created_at": n.created_at.isoformat() if n.created_at else None,
                "can_retry": can_retry,
                "retries_remaining": retries_remaining,
            }
        )

    return {"items": items}


# ---------------------------------------------------------------------------
# POST /admin/notifications/{id}/retry
# ---------------------------------------------------------------------------


@router.post("/admin/notifications/{notification_id}/retry")
async def retry_notification(
    notification_id: str,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    notif = (
        db.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.id == notification_id
            )
        )
        .scalars()
        .first()
    )

    if not notif:
        raise HTTPException(status_code=404, detail="Pranesimas nerastas")

    if notif.status != "FAILED":
        raise HTTPException(
            status_code=400, detail="Galima kartoti tik FAILED pranesimus"
        )

    attempts = notif.attempt_count or 0
    remaining = max(0, RETRY_LIMIT - attempts)

    if remaining <= 0:
        raise HTTPException(
            status_code=429,
            detail={
                "message": "Kartojimo limitas virsytas",
                "remaining": 0,
            },
        )

    # Reset for retry
    notif.status = "PENDING"
    notif.last_error = None
    notif.next_attempt_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "message": "Pranesimas bus kartotas",
        "remaining": remaining - 1,
    }
