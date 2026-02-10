"""Admin read-model helpers — aggregation and view-model builders.

All client PII is returned **masked**. There is NO endpoint that returns raw
email or phone. This is a non-negotiable MVP contract.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.project import (
    ClientConfirmation,
    NotificationOutbox,
    Payment,
    Project,
)

# ---------------------------------------------------------------------------
# PII masking (server-side, always applied)
# ---------------------------------------------------------------------------


def mask_email(email: str | None) -> str:
    if not email:
        return "-"
    parts = email.split("@")
    if len(parts) != 2:
        return email[0] + "***" if email else "-"
    local, domain = parts
    domain_parts = domain.split(".")
    masked_local = local[0] + "***" if local else "***"
    masked_domain = domain_parts[0][0] + "***" if domain_parts[0] else "***"
    suffix = ".".join(domain_parts[1:]) if len(domain_parts) > 1 else ""
    return f"{masked_local}@{masked_domain}.{suffix}" if suffix else f"{masked_local}@{masked_domain}"


def mask_phone(phone: str | None) -> str:
    if not phone:
        return "-"
    clean = phone.replace(" ", "")
    if len(clean) < 6:
        return clean[0] + "***" if clean else "-"
    return clean[:4] + "*" * (len(clean) - 6) + clean[-2:]


# ---------------------------------------------------------------------------
# Client key derivation
# ---------------------------------------------------------------------------

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    return email.strip().lower() or None


def _normalize_phone(phone: str | None) -> str | None:
    """Best-effort E.164 normalization."""
    if not phone:
        return None
    clean = re.sub(r"[^+\d]", "", phone.strip())
    if not clean or len(clean) < 6:
        return None
    return clean


def derive_client_key(client_info: dict | None) -> tuple[str, str]:
    """Return (client_key, confidence) from a project's client_info JSON.

    confidence: HIGH (client_id is UUID), MEDIUM (email+phone hash), LOW (single field hash).
    """
    if not client_info:
        return ("unknown", "LOW")

    # Priority 1: client_id if valid UUID
    client_id = client_info.get("client_id") or client_info.get("user_id") or client_info.get("id") or ""
    if client_id and _UUID_RE.match(str(client_id)):
        return (str(client_id), "HIGH")

    # Priority 2-4: hash-based
    email = _normalize_email(client_info.get("email"))
    phone = _normalize_phone(client_info.get("phone"))

    if email and phone:
        raw = f"{email}|{phone}"
        return (hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16], "MEDIUM")

    if email:
        return (hashlib.sha256(email.encode("utf-8")).hexdigest()[:16], "LOW")

    if phone:
        return (hashlib.sha256(phone.encode("utf-8")).hexdigest()[:16], "LOW")

    return ("unknown", "LOW")


def _display_name(client_info: dict | None) -> str:
    if not client_info:
        return "-"
    return client_info.get("name") or client_info.get("client_name") or "-"


def _contact_masked(client_info: dict | None) -> str:
    if not client_info:
        return "-"
    email = mask_email(client_info.get("email"))
    phone = mask_phone(client_info.get("phone"))
    parts = []
    if email != "-":
        parts.append(email)
    if phone != "-":
        parts.append(phone)
    return " / ".join(parts) or "-"


# ---------------------------------------------------------------------------
# Attention flags
# ---------------------------------------------------------------------------

# Priority order (lower = higher priority)
ATTENTION_PRIORITY = {
    "pending_confirmation": 1,
    "failed_outbox": 2,
    "missing_deposit": 3,
    "missing_final": 4,
    "stale_paid_no_schedule": 5,
}


def _compute_attention_flags(project: Project, db: Session) -> list[str]:
    """Compute attention flags for a single project, sorted by priority."""
    flags = []
    status = project.status

    if status == "DRAFT":
        # Check no deposit payment
        has_deposit = (
            db.execute(
                select(Payment.id)
                .where(Payment.project_id == project.id)
                .where(Payment.payment_type == "DEPOSIT")
                .where(Payment.status == "SUCCEEDED")
                .limit(1)
            ).first()
            is not None
        )
        if not has_deposit:
            flags.append("missing_deposit")

    elif status == "PAID":
        # Paid but not scheduled
        flags.append("stale_paid_no_schedule")

    elif status == "CERTIFIED":
        # Check final payment
        has_final = (
            db.execute(
                select(Payment.id)
                .where(Payment.project_id == project.id)
                .where(Payment.payment_type == "FINAL")
                .where(Payment.status == "SUCCEEDED")
                .limit(1)
            ).first()
            is not None
        )
        if not has_final:
            flags.append("missing_final")
        else:
            # Final paid — check confirmation
            has_confirmed = (
                db.execute(
                    select(ClientConfirmation.id)
                    .where(ClientConfirmation.project_id == project.id)
                    .where(ClientConfirmation.status == "CONFIRMED")
                    .limit(1)
                ).first()
                is not None
            )
            if not has_confirmed:
                flags.append("pending_confirmation")

    # Check failed outbox for any status
    has_failed_outbox = (
        db.execute(
            select(NotificationOutbox.id)
            .where(NotificationOutbox.entity_type == "project")
            .where(NotificationOutbox.entity_id == str(project.id))
            .where(NotificationOutbox.status == "FAILED")
            .limit(1)
        ).first()
        is not None
    )
    if has_failed_outbox:
        flags.append("failed_outbox")

    # Sort by priority
    flags.sort(key=lambda f: ATTENTION_PRIORITY.get(f, 99))
    return flags


def _deposit_state(project: Project, db: Session) -> str:
    has_deposit = (
        db.execute(
            select(Payment.id)
            .where(Payment.project_id == project.id)
            .where(Payment.payment_type == "DEPOSIT")
            .where(Payment.status == "SUCCEEDED")
            .limit(1)
        ).first()
        is not None
    )
    return "PAID" if has_deposit else "PENDING"


def _final_state(project: Project, db: Session) -> str:
    has_final = (
        db.execute(
            select(Payment.id)
            .where(Payment.project_id == project.id)
            .where(Payment.payment_type == "FINAL")
            .where(Payment.status == "SUCCEEDED")
            .limit(1)
        ).first()
        is not None
    )
    if not has_final:
        return "PENDING"

    has_confirmed = (
        db.execute(
            select(ClientConfirmation.id)
            .where(ClientConfirmation.project_id == project.id)
            .where(ClientConfirmation.status == "CONFIRMED")
            .limit(1)
        ).first()
        is not None
    )
    return "CONFIRMED" if has_confirmed else "AWAITING_CONFIRMATION"


# ---------------------------------------------------------------------------
# Customer list aggregation
# ---------------------------------------------------------------------------


def build_customer_list(
    db: Session,
    *,
    attention_only: bool = True,
    limit: int = 50,
    last_activity_from: datetime | None = None,
) -> list[dict[str, Any]]:
    """Build aggregated customer list from projects.

    Groups projects by derived client_key. Returns masked PII only.
    """
    # Default time window: 12 months
    if last_activity_from is None and not attention_only:
        last_activity_from = datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year - 1)

    stmt = select(Project).order_by(desc(Project.updated_at))
    if last_activity_from is not None:
        stmt = stmt.where(Project.updated_at >= last_activity_from)

    projects = db.execute(stmt).scalars().all()

    # Group by client_key
    groups: dict[str, list[Project]] = {}
    key_meta: dict[str, tuple[str, dict]] = {}  # client_key -> (confidence, client_info)

    for p in projects:
        ck, conf = derive_client_key(p.client_info)
        if ck not in groups:
            groups[ck] = []
            key_meta[ck] = (conf, p.client_info or {})
        groups[ck].append(p)

    # Build output
    result = []
    for ck, projs in groups.items():
        conf, ci = key_meta[ck]
        latest = projs[0]  # Already sorted by updated_at desc

        # Compute attention flags from most recent project
        all_flags: list[str] = []
        for p in projs:
            all_flags.extend(_compute_attention_flags(p, db))
        # Dedupe + sort
        seen = set()
        unique_flags = []
        for f in all_flags:
            if f not in seen:
                seen.add(f)
                unique_flags.append(f)
        unique_flags.sort(key=lambda f: ATTENTION_PRIORITY.get(f, 99))

        if attention_only and not unique_flags:
            continue

        result.append(
            {
                "client_key": ck,
                "client_key_confidence": conf,
                "display_name": _display_name(ci),
                "contact_masked": _contact_masked(ci),
                "project_count": len(projs),
                "last_project": {
                    "id": str(latest.id),
                    "status": latest.status,
                },
                "deposit_state": _deposit_state(latest, db),
                "final_state": _final_state(latest, db),
                "attention_flags": unique_flags,
                "last_activity": (latest.updated_at.isoformat() if latest.updated_at else None),
            }
        )

    # Sort by attention (has flags first), then by last_activity desc
    result.sort(
        key=lambda c: (
            0 if c["attention_flags"] else 1,
            c.get("last_activity") or "",
        ),
        reverse=False,
    )
    result.sort(key=lambda c: c.get("last_activity") or "", reverse=True)
    result.sort(key=lambda c: 0 if c["attention_flags"] else 1)

    return result[:limit]


# ---------------------------------------------------------------------------
# Customer profile (view model)
# ---------------------------------------------------------------------------


def _actions_available(project: Project, db: Session) -> list[str]:
    """Determine which workflow actions are available for a project."""
    status = project.status
    actions = []

    if status == "DRAFT":
        actions.append("record_deposit")
    elif status == "PAID":
        actions.append("schedule_visit")
    elif status == "SCHEDULED":
        actions.append("assign_expert")
    elif status == "PENDING_EXPERT":
        actions.append("certify_project")
    elif status == "CERTIFIED":
        has_final = _final_state(project, db) != "PENDING"
        if not has_final:
            actions.append("record_final_payment")
        else:
            final_st = _final_state(project, db)
            if final_st == "AWAITING_CONFIRMATION":
                actions.append("resend_confirmation")
            actions.append("override_activate")

    return actions


def _compute_next_best_action(projects: list[Project], db: Session) -> dict | None:
    """Compute the next best action across all client projects.

    Never returns override_activate.
    """
    for p in projects:
        status = p.status
        if status == "DRAFT":
            has_dep = _deposit_state(p, db) == "PAID"
            if not has_dep:
                return {
                    "type": "record_deposit",
                    "project_id": str(p.id),
                    "label": "Irasyti depozita",
                }
        elif status == "PAID":
            return {
                "type": "schedule_visit",
                "project_id": str(p.id),
                "label": "Suplanuoti vizita",
            }
        elif status == "CERTIFIED":
            fs = _final_state(p, db)
            if fs == "PENDING":
                return {
                    "type": "record_final",
                    "project_id": str(p.id),
                    "label": "Irasyti galutini mokejima",
                }
            if fs == "AWAITING_CONFIRMATION":
                return {
                    "type": "resend_confirmation",
                    "project_id": str(p.id),
                    "label": "Persiusti patvirtinima",
                }
    return None


def build_customer_profile(
    db: Session,
    client_key: str,
    settings: Any = None,
) -> dict[str, Any] | None:
    """Build full customer profile view model.

    Returns None if no matching projects found.
    """
    # Find all projects matching this client_key
    all_projects = db.execute(select(Project).order_by(desc(Project.updated_at))).scalars().all()

    matching = []
    client_info_sample: dict = {}
    for p in all_projects:
        ck, _ = derive_client_key(p.client_info)
        if ck == client_key:
            matching.append(p)
            if not client_info_sample and p.client_info:
                client_info_sample = p.client_info

    if not matching:
        return None

    # Build project list with actions
    proj_list = []
    for p in matching:
        proj_list.append(
            {
                "id": str(p.id),
                "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                "deposit_state": _deposit_state(p, db),
                "final_state": _final_state(p, db),
                "actions_available": _actions_available(p, db),
                "area_m2": p.area_m2,
            }
        )

    # Attention flags
    all_flags: list[str] = []
    for p in matching:
        all_flags.extend(_compute_attention_flags(p, db))
    seen = set()
    unique_flags = []
    for f in all_flags:
        if f not in seen:
            seen.add(f)
            unique_flags.append(f)
    unique_flags.sort(key=lambda f: ATTENTION_PRIORITY.get(f, 99))

    # Summary
    total_paid = 0.0
    for p in matching:
        payments = (
            db.execute(select(Payment).where(Payment.project_id == p.id).where(Payment.status == "SUCCEEDED"))
            .scalars()
            .all()
        )
        for pay in payments:
            total_paid += float(pay.amount or 0)

    # Feature flags
    feature_flags = {}
    if settings:
        feature_flags = {
            "finance_ledger": getattr(settings, "enable_finance_ledger", False),
            "finance_ai_ingest": getattr(settings, "enable_finance_ai_ingest", False),
        }

    return {
        "client_key": client_key,
        "client_info": {
            "display_name": _display_name(client_info_sample),
            "contact_masked": _contact_masked(client_info_sample),
        },
        "projects": proj_list,
        "next_best_action": _compute_next_best_action(matching, db),
        "attention_flags": unique_flags,
        "summary": {
            "total_projects": len(matching),
            "total_paid": total_paid,
        },
        "feature_flags": feature_flags,
    }
