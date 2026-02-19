"""Admin project detail endpoints: payments, confirmations, notifications, resend, retry.

Contract notes:
- UI must not receive raw PII (email/phone).
- Resend/Retry are rate limited: max 3 per 24h, surfaced via remaining/reset_at.
- Rate limit counters are stored in AuditLog (persistent, restart-safe).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.models.project import AuditLog, ClientConfirmation, NotificationOutbox, Payment, Project
from app.services.email_templates import build_email_payload
from app.services.notification_outbox import enqueue_notification
from app.services.transition_service import create_audit_log, create_client_confirmation
from app.utils.rate_limit import get_user_agent

router = APIRouter()

RESEND_LIMIT = 3
RESEND_WINDOW_HOURS = 24
RETRY_LIMIT = 3
RETRY_WINDOW_HOURS = 24


def _dialect_name(db: Session) -> str:
    dialect = getattr(getattr(db, "bind", None), "dialect", None)
    return (getattr(dialect, "name", "") or "").lower()


def _now_utc(db: Session) -> datetime:
    dt = datetime.now(timezone.utc)
    # SQLite stores timezone-aware datetimes as naive values.
    if _dialect_name(db) == "sqlite":
        return dt.replace(tzinfo=None)
    return dt


def _ip_real(request: Request) -> str | None:
    ip = (request.headers.get("x-real-ip") or "").strip()
    return ip or None


def _get_project_or_404(db: Session, project_id: str) -> Project:
    project = db.execute(select(Project).where(Project.id == project_id)).scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Projektas nerastas")
    return project


def _build_final_payment_confirmation_url(token: str) -> str:
    settings = get_settings()
    base_url = (settings.public_base_url or "https://vejapro.lt").rstrip("/")
    return f"{base_url}/api/v1/public/confirm-payment/{quote(token)}"


def _window_usage(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    window_hours: int,
) -> tuple[int, str]:
    """Return (used_in_window, reset_at_iso). Uses AuditLog for persistence."""
    now = _now_utc(db)
    cutoff = now - timedelta(hours=int(window_hours))
    try:
        entity_uuid = uuid.UUID(str(entity_id))
    except ValueError:
        return (0, (now + timedelta(hours=int(window_hours))).isoformat())

    timestamps = (
        db.execute(
            select(AuditLog.timestamp)
            .where(AuditLog.entity_type == entity_type)
            .where(AuditLog.entity_id == entity_uuid)
            .where(AuditLog.action == action)
            .where(AuditLog.timestamp >= cutoff)
            .order_by(AuditLog.timestamp.asc())
        )
        .scalars()
        .all()
    )
    used = len(timestamps)
    reset_at = (
        (timestamps[0] + timedelta(hours=int(window_hours))) if used else (now + timedelta(hours=int(window_hours)))
    )
    return used, reset_at.isoformat()


@router.get("/admin/projects/{project_id}/payments")
async def get_project_payments(
    project_id: str,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _get_project_or_404(db, project_id)
    payments = (
        db.execute(select(Payment).where(Payment.project_id == project_id).order_by(desc(Payment.created_at)))
        .scalars()
        .all()
    )
    items: list[dict] = []
    for p in payments:
        items.append(
            {
                "id": str(p.id),
                "payment_type": p.payment_type,
                "amount": float(p.amount) if p.amount is not None else None,
                "currency": p.currency or "EUR",
                "status": p.status,
                "payment_method": p.payment_method,
                "received_at": p.received_at.isoformat() if p.received_at else None,
                "proof_url": p.proof_url,
                "provider_event_id": p.provider_event_id,
            }
        )
    return {"items": items}


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

    items: list[dict] = []
    for c in confirmations:
        channel = (c.channel or "email").strip().lower()
        used, reset_at = _window_usage(
            db,
            entity_type="project",
            entity_id=str(project_id),
            action=f"ADMIN_CONFIRMATION_RESEND_{channel.upper()}",
            window_hours=RESEND_WINDOW_HOURS,
        )
        remaining = max(0, RESEND_LIMIT - used)
        items.append(
            {
                "id": str(c.id),
                "channel": channel,
                "status": c.status,
                "attempts": c.attempts,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "expires_at": c.expires_at.isoformat() if c.expires_at else None,
                "can_resend": remaining > 0 and c.status != "CONFIRMED",
                "resends_remaining": remaining,
                "reset_at": reset_at,
            }
        )
    return {"items": items}


class ResendRequest(BaseModel):
    channel: str = "email"


@router.post("/admin/projects/{project_id}/confirmations/resend")
async def resend_confirmation(
    project_id: str,
    request: Request,
    payload: ResendRequest = ResendRequest(),
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(db, project_id)
    channel = (payload.channel or "email").strip().lower()
    if channel not in {"email", "sms"}:
        raise HTTPException(status_code=400, detail="Nepalaikomas kanalas")

    # Pre-condition: a confirmation exists for this project.
    exists = (
        db.execute(select(ClientConfirmation.id).where(ClientConfirmation.project_id == project_id).limit(1))
        .scalars()
        .first()
    )
    if not exists:
        raise HTTPException(status_code=400, detail="Patvirtinimo irasas nerastas")

    used, reset_at = _window_usage(
        db,
        entity_type="project",
        entity_id=str(project_id),
        action=f"ADMIN_CONFIRMATION_RESEND_{channel.upper()}",
        window_hours=RESEND_WINDOW_HOURS,
    )
    remaining_before = max(0, RESEND_LIMIT - used)
    if remaining_before <= 0:
        raise HTTPException(
            status_code=429,
            detail={"message": "Persiuntimo limitas virsytas", "remaining": 0, "reset_at": reset_at},
        )

    # Create new confirmation token (DB stores hash only).
    token = create_client_confirmation(db, str(project_id), channel=channel)

    client_info = project.client_info if isinstance(project.client_info, dict) else {}
    if channel == "email":
        to_email = (client_info.get("email") or "").strip()
        if not to_email:
            raise HTTPException(status_code=400, detail="Kliento el. pastas nerastas")
        enqueue_notification(
            db,
            entity_type="project",
            entity_id=str(project_id),
            channel="email",
            template_key="FINAL_PAYMENT_CONFIRMATION",
            payload_json=build_email_payload(
                "FINAL_PAYMENT_CONFIRMATION",
                to=to_email,
                token=token,
                confirmation_url=_build_final_payment_confirmation_url(token),
            ),
        )
    else:
        to_number = (client_info.get("phone") or "").strip()
        if not to_number:
            raise HTTPException(status_code=400, detail="Kliento telefonas nerastas")
        enqueue_notification(
            db,
            entity_type="project",
            entity_id=str(project_id),
            channel="sms",
            template_key="FINAL_PAYMENT_CONFIRMATION",
            payload_json={
                "to_number": to_number,
                "body": f"VejaPRO patvirtinimo kodas: {token}",
            },
        )

    create_audit_log(
        db,
        entity_type="project",
        entity_id=str(project_id),
        action=f"ADMIN_CONFIRMATION_RESEND_{channel.upper()}",
        old_value=None,
        new_value={"channel": channel},
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_ip_real(request),
        user_agent=get_user_agent(request),
    )
    db.commit()

    return {"remaining": remaining_before - 1, "reset_at": reset_at}


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

    items: list[dict] = []
    for n in notifications:
        used, reset_at = _window_usage(
            db,
            entity_type="notification_outbox",
            entity_id=str(n.id),
            action="ADMIN_NOTIFICATION_RETRY",
            window_hours=RETRY_WINDOW_HOURS,
        )
        retries_remaining = max(0, RETRY_LIMIT - used)
        can_retry = n.status == "FAILED" and retries_remaining > 0
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
                "reset_at": reset_at,
            }
        )
    return {"items": items}


@router.post("/admin/notifications/{notification_id}/retry")
async def retry_notification(
    notification_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    notif = db.execute(select(NotificationOutbox).where(NotificationOutbox.id == notification_id)).scalars().first()
    if not notif:
        raise HTTPException(status_code=404, detail="Pranesimas nerastas")
    if notif.status != "FAILED":
        raise HTTPException(status_code=400, detail="Galima kartoti tik FAILED pranesimus")

    used, reset_at = _window_usage(
        db,
        entity_type="notification_outbox",
        entity_id=str(notification_id),
        action="ADMIN_NOTIFICATION_RETRY",
        window_hours=RETRY_WINDOW_HOURS,
    )
    remaining_before = max(0, RETRY_LIMIT - used)
    if remaining_before <= 0:
        raise HTTPException(
            status_code=429,
            detail={"message": "Kartojimo limitas virsytas", "remaining": 0, "reset_at": reset_at},
        )

    notif.status = "PENDING"
    notif.last_error = None
    notif.attempt_count = 0
    notif.next_attempt_at = _now_utc(db)

    create_audit_log(
        db,
        entity_type="notification_outbox",
        entity_id=str(notification_id),
        action="ADMIN_NOTIFICATION_RETRY",
        old_value=None,
        new_value=None,
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_ip_real(request),
        user_agent=get_user_agent(request),
    )
    db.commit()

    return {"remaining": remaining_before - 1, "reset_at": reset_at}
