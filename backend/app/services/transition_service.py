import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import hashlib
import secrets

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.project import Project, AuditLog, SmsConfirmation, Payment, Evidence
from app.schemas.project import ProjectStatus
from app.utils.alerting import alert_tracker

logger = logging.getLogger(__name__)


ALLOWED_TRANSITIONS = {
    ProjectStatus.DRAFT: [ProjectStatus.PAID],
    ProjectStatus.PAID: [ProjectStatus.SCHEDULED],
    ProjectStatus.SCHEDULED: [ProjectStatus.PENDING_EXPERT],
    ProjectStatus.PENDING_EXPERT: [ProjectStatus.CERTIFIED],
    ProjectStatus.CERTIFIED: [ProjectStatus.ACTIVE],
    ProjectStatus.ACTIVE: [],
}

PII_REDACTION_FALLBACK_FIELDS = {
    "phone",
    "email",
    "address",
    "ssn",
    "tax_id",
    "passport",
    "national_id",
    "id_number",
}


def _redact_pii(value: Any, redact_keys: set[str]) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in redact_keys:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact_pii(item, redact_keys)
        return redacted
    if isinstance(value, list):
        return [_redact_pii(item, redact_keys) for item in value]
    return value


def create_audit_log(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    old_value: Optional[Dict[str, Any]],
    new_value: Optional[Dict[str, Any]],
    actor_type: str,
    actor_id: Optional[str],
    ip_address: Optional[str],
    user_agent: Optional[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    settings = get_settings()
    if settings.pii_redaction_enabled:
        configured = {item.lower() for item in settings.pii_redaction_fields}
        redact_keys = configured or set(PII_REDACTION_FALLBACK_FIELDS)
        old_value = _redact_pii(old_value, redact_keys)
        new_value = _redact_pii(new_value, redact_keys)
        if metadata is not None:
            metadata = _redact_pii(metadata, redact_keys)

    log = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_value=old_value,
        new_value=new_value,
        actor_type=actor_type,
        actor_id=actor_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=metadata,
    )
    db.add(log)
    try:
        alert_tracker.record(action, metadata)
    except Exception:
        logger.exception("Alert tracker failed for action=%s", action)


def _is_allowed_actor(current: ProjectStatus, new: ProjectStatus, actor_type: str) -> bool:
    if current == ProjectStatus.DRAFT and new == ProjectStatus.PAID:
        return actor_type == "SYSTEM_STRIPE"
    if current == ProjectStatus.PAID and new == ProjectStatus.SCHEDULED:
        return actor_type in {"SUBCONTRACTOR", "ADMIN"}
    if current == ProjectStatus.SCHEDULED and new == ProjectStatus.PENDING_EXPERT:
        return actor_type in {"SUBCONTRACTOR", "ADMIN"}
    if current == ProjectStatus.PENDING_EXPERT and new == ProjectStatus.CERTIFIED:
        return actor_type in {"EXPERT", "ADMIN"}
    if current == ProjectStatus.CERTIFIED and new == ProjectStatus.ACTIVE:
        return actor_type == "SYSTEM_TWILIO"
    return False


def apply_transition(
    db: Session,
    *,
    project: Project,
    new_status: ProjectStatus,
    actor_type: str,
    actor_id: Optional[str],
    ip_address: Optional[str],
    user_agent: Optional[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    current = ProjectStatus(project.status)

    if new_status == current:
        return False

    if new_status not in ALLOWED_TRANSITIONS.get(current, []):
        raise HTTPException(400, f"Negalimas perejimas: {current} -> {new_status}")

    if not _is_allowed_actor(current, new_status, actor_type):
        raise HTTPException(403, "Forbidden")

    if new_status == ProjectStatus.CERTIFIED:
        checklist = (metadata or {}).get("checklist")
        if not checklist:
            raise HTTPException(400, "Checklist required")
        evidence_count = (
            db.query(Evidence)
            .filter(
                Evidence.project_id == project.id,
                Evidence.category == "EXPERT_CERTIFICATION",
            )
            .count()
        )
        if evidence_count < 3:
            raise HTTPException(400, "Need at least 3 certification photos")

    if new_status == ProjectStatus.ACTIVE:
        if not is_final_payment_recorded(db, str(project.id)):
            raise HTTPException(400, "Final payment not recorded")

    old_status = project.status
    project.status = new_status.value
    project.status_changed_at = datetime.now(timezone.utc)

    if new_status in {ProjectStatus.CERTIFIED, ProjectStatus.ACTIVE}:
        project.is_certified = True

    create_audit_log(
        db,
        entity_type="project",
        entity_id=str(project.id),
        action="STATUS_CHANGE",
        old_value={"status": old_status},
        new_value={"status": project.status},
        actor_type=actor_type,
        actor_id=actor_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=metadata,
    )
    return True


def create_sms_confirmation(db: Session, project_id: str, ttl_hours: int = 72) -> str:
    token = secrets.token_urlsafe(8).upper()
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

    confirmation = SmsConfirmation(
        project_id=project_id,
        token_hash=token_hash,
        expires_at=expires_at,
        status="PENDING",
        attempts=0,
    )
    db.add(confirmation)
    return token


def increment_sms_attempt(db: Session, confirmation: SmsConfirmation) -> None:
    confirmation.attempts = (confirmation.attempts or 0) + 1


def find_sms_confirmation(db: Session, token: str) -> Optional[SmsConfirmation]:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return (
        db.query(SmsConfirmation)
        .filter(SmsConfirmation.token_hash == token_hash)
        .one_or_none()
    )


def is_final_payment_recorded(db: Session, project_id: str) -> bool:
    payment = (
        db.query(Payment)
        .filter(
            Payment.project_id == project_id,
            Payment.payment_type == "FINAL",
            Payment.status == "SUCCEEDED",
        )
        .first()
    )
    return payment is not None


def unpublish_project_evidences(db: Session, project_id: str, actor_type: str, actor_id: Optional[str], ip_address: Optional[str], user_agent: Optional[str]) -> int:
    evidences = db.query(Evidence).filter(Evidence.project_id == project_id, Evidence.show_on_web.is_(True)).all()
    for ev in evidences:
        ev.show_on_web = False
    if evidences:
        create_audit_log(
            db,
            entity_type="project",
            entity_id=project_id,
            action="MARKETING_CONSENT_REVOKE",
            old_value={"show_on_web": True},
            new_value={"show_on_web": False},
            actor_type=actor_type,
            actor_id=actor_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"affected_evidences": len(evidences)},
        )
    return len(evidences)
