"""Admin read-model helpers — aggregation and view-model builders.

All client PII is returned **masked**. There is NO endpoint that returns raw
email or phone. This is a non-negotiable MVP contract.
"""

from __future__ import annotations

import base64
import hashlib
import re
from datetime import datetime, timedelta, timezone
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
    """Best-effort E.164 normalization.

    Contract: if we cannot confidently parse to E.164, we MUST ignore phone
    for client_key derivation (prevents accidental collisions).
    """
    if not phone:
        return None
    clean = re.sub(r"[^\d+]", "", phone.strip())
    if not clean:
        return None
    if clean.startswith("00"):
        clean = "+" + clean[2:]
    if not clean.startswith("+"):
        return None
    digits = clean[1:]
    if not digits.isdigit():
        return None
    # E.164 max 15 digits (excluding '+'). Keep a conservative min bound.
    if not (8 <= len(digits) <= 15):
        return None
    return "+" + digits


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
        return (hashlib.sha256(raw.encode("utf-8")).hexdigest(), "MEDIUM")

    if email:
        return (hashlib.sha256(email.encode("utf-8")).hexdigest(), "LOW")

    if phone:
        return (hashlib.sha256(phone.encode("utf-8")).hexdigest(), "LOW")

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
        if not project.scheduled_for:
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

def _dialect_name(db: Session) -> str:
    dialect = getattr(getattr(db, "bind", None), "dialect", None)
    return (getattr(dialect, "name", "") or "").lower()


def _as_db_dt(db: Session, dt: datetime) -> datetime:
    """Normalize datetime to match DB storage semantics (SQLite stores naive)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)
    if _dialect_name(db) == "sqlite":
        return dt_utc.replace(tzinfo=None)
    return dt_utc


def _now_utc(db: Session) -> datetime:
    return _as_db_dt(db, datetime.now(timezone.utc))


def _parse_iso_dt(value: str) -> datetime:
    raw = (value or "").strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_utc(dt: datetime | None) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _encode_customer_cursor(*, as_of: datetime, last_activity: datetime, client_key: str) -> str:
    payload = f"{as_of.isoformat()}|{last_activity.isoformat()}|{client_key}".encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("utf-8")


def _decode_customer_cursor(value: str) -> tuple[datetime, datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(value.encode("utf-8")).decode("utf-8")
        as_of_raw, last_raw, client_key = raw.split("|", 2)
        return (_parse_iso_dt(as_of_raw), _parse_iso_dt(last_raw), client_key)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Invalid cursor") from exc


def build_customer_list(
    db: Session,
    *,
    attention_only: bool = True,
    limit: int = 50,
    cursor: str | None = None,
    as_of: datetime | None = None,
    attention: str | None = None,
    project_status: str | None = None,
    financial_state: str | None = None,
    last_activity_from: datetime | None = None,
    last_activity_to: datetime | None = None,
) -> dict[str, Any]:
    """Build aggregated customer list from projects.

    Groups projects by derived client_key. Returns masked PII only.
    """
    if limit < 1:
        limit = 1

    # Cursor contract: cursor is bound to as_of snapshot.
    cursor_as_of = None
    cursor_last = None
    cursor_ck = None
    if cursor:
        try:
            cursor_as_of, cursor_last, cursor_ck = _decode_customer_cursor(cursor)
        except ValueError as err:
            raise ValueError("Invalid cursor") from err

    if as_of is None:
        as_of = cursor_as_of or datetime.now(timezone.utc)
    else:
        if cursor_as_of and _parse_iso_dt(as_of.isoformat()) != cursor_as_of:
            raise ValueError("Cursor/as_of mismatch")

    # Default time window: 12 months for "show all" mode.
    if last_activity_from is None and not attention_only:
        last_activity_from = (as_of - timedelta(days=365))

    as_of_db = _as_db_dt(db, as_of)
    stmt = select(Project).where(Project.updated_at <= as_of_db).order_by(desc(Project.updated_at), desc(Project.id))
    if last_activity_from is not None:
        stmt = stmt.where(Project.updated_at >= _as_db_dt(db, last_activity_from))
    if last_activity_to is not None:
        stmt = stmt.where(Project.updated_at <= _as_db_dt(db, last_activity_to))

    projects = db.execute(stmt).scalars().all()

    # Group by client_key
    groups: dict[str, list[Project]] = {}
    key_meta: dict[str, tuple[str, dict]] = {}  # client_key -> (confidence, client_info)
    last_activity_by_ck: dict[str, datetime] = {}

    for p in projects:
        ck, conf = derive_client_key(p.client_info)
        if ck not in groups:
            groups[ck] = []
            key_meta[ck] = (conf, p.client_info or {})
            if p.updated_at:
                last_activity_by_ck[ck] = p.updated_at
        groups[ck].append(p)

    # Build output
    result: list[dict[str, Any]] = []
    for ck, projs in groups.items():
        conf, ci = key_meta[ck]
        # projs are appended in updated_at desc order (because the source query is).
        latest = projs[0]
        last_activity_dt = last_activity_by_ck.get(ck) or latest.updated_at

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
        if attention and attention not in unique_flags:
            continue
        if project_status and (latest.status or "") != project_status:
            continue

        dep_state = _deposit_state(latest, db)
        fin_state = _final_state(latest, db)
        if financial_state:
            fs = financial_state
            if fs in ATTENTION_PRIORITY and fs not in unique_flags:
                continue
            elif fs == "missing_deposit" and not (latest.status == "DRAFT" and dep_state != "PAID"):
                continue
            elif fs == "missing_final" and not (latest.status == "CERTIFIED" and fin_state == "PENDING"):
                continue
            elif fs in ("awaiting_confirmation", "pending_confirmation") and fin_state != "AWAITING_CONFIRMATION":
                continue
            elif fs == "confirmed" and fin_state != "CONFIRMED":
                continue
            elif fs == "paid" and dep_state != "PAID":
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
                "deposit_state": dep_state,
                "final_state": fin_state,
                "attention_flags": unique_flags,
                "last_activity": _iso_utc(last_activity_dt),
                # Optional hint for list UI actions.
                "next_best_action": _compute_next_best_action(projs, db),
            }
        )

    # Sort: last_activity DESC, client_key DESC
    def _sort_key(item: dict[str, Any]) -> tuple[str, str]:
        # ISO strings sort lexicographically for UTC timestamps.
        return (item.get("last_activity") or "", item.get("client_key") or "")

    result.sort(key=_sort_key, reverse=True)

    # Apply cursor (seek after the last item of previous page)
    if cursor_last is not None and cursor_ck is not None:
        last_iso = cursor_last.isoformat()
        filtered = []
        for item in result:
            la = item.get("last_activity") or ""
            ck = item.get("client_key") or ""
            if la < last_iso or (la == last_iso and ck < cursor_ck):
                filtered.append(item)
        result = filtered

    page = result[: limit + 1]
    has_more = len(page) > limit
    page = page[:limit]

    next_cursor = None
    if has_more and page:
        last_item = page[-1]
        last_activity = _parse_iso_dt(last_item["last_activity"]) if last_item.get("last_activity") else as_of
        next_cursor = _encode_customer_cursor(
            as_of=_parse_iso_dt(as_of.isoformat()),
            last_activity=last_activity,
            client_key=str(last_item["client_key"]),
        )

    return {
        "items": page,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "as_of": _parse_iso_dt(as_of.isoformat()).isoformat(),
    }


def count_unique_clients_12m(db: Session, *, as_of: datetime | None = None) -> dict[str, Any]:
    """Count unique derived client keys based on projects created in last 12 months."""
    if as_of is None:
        as_of = datetime.now(timezone.utc)
    start = as_of - timedelta(days=365)
    stmt = (
        select(Project.client_info)
        .where(Project.created_at >= _as_db_dt(db, start))
        .where(Project.created_at <= _as_db_dt(db, as_of))
    )
    rows = db.execute(stmt).all()
    keys = set()
    for (ci,) in rows:
        ck, _ = derive_client_key(ci if isinstance(ci, dict) else None)
        keys.add(ck)
    # Do not count unknown placeholder
    keys.discard("unknown")
    return {"unique_clients_12m": len(keys), "as_of": _parse_iso_dt(as_of.isoformat()).isoformat()}


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
                "created_at": _iso_utc(p.created_at),
                "updated_at": _iso_utc(p.updated_at),
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
