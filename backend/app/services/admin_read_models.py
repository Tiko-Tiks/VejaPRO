"""Admin read-model helpers — aggregation and view-model builders.

All client PII is returned **masked**. There is NO endpoint that returns raw
email or phone. This is a non-negotiable MVP contract.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.project import (
    AuditLog,
    CallRequest,
    ClientConfirmation,
    NotificationOutbox,
    Payment,
    Project,
)

# ---------------------------------------------------------------------------
# Batch prefetch cache — eliminates N+1 queries on listing pages
# ---------------------------------------------------------------------------


@dataclass
class _ProjectLookups:
    """Pre-fetched lookup tables for batch computation of attention flags,
    deposit/final states, and confirmations. One instance per request.
    """

    deposit_paid: set[UUID] = field(default_factory=set)
    final_paid: set[UUID] = field(default_factory=set)
    confirmed: set[UUID] = field(default_factory=set)
    failed_outbox: set[UUID] = field(default_factory=set)


def _prefetch_project_lookups(db: Session, project_ids: list[UUID]) -> _ProjectLookups:
    """Run 4 batch queries (instead of N×4 individual ones).

    Returns a lookup object usable by the _cached variants of attention/state helpers.
    """
    if not project_ids:
        return _ProjectLookups()

    lookups = _ProjectLookups()

    # 1. Deposits paid
    deposit_rows = db.execute(
        select(Payment.project_id)
        .where(Payment.project_id.in_(project_ids))
        .where(Payment.payment_type == "DEPOSIT")
        .where(Payment.status == "SUCCEEDED")
    ).all()
    lookups.deposit_paid = {row[0] for row in deposit_rows}

    # 2. Finals paid
    final_rows = db.execute(
        select(Payment.project_id)
        .where(Payment.project_id.in_(project_ids))
        .where(Payment.payment_type == "FINAL")
        .where(Payment.status == "SUCCEEDED")
    ).all()
    lookups.final_paid = {row[0] for row in final_rows}

    # 3. Confirmed client confirmations
    conf_rows = db.execute(
        select(ClientConfirmation.project_id)
        .where(ClientConfirmation.project_id.in_(project_ids))
        .where(ClientConfirmation.status == "CONFIRMED")
    ).all()
    lookups.confirmed = {row[0] for row in conf_rows}

    # 4. Failed outbox (entity_id is str UUID)
    str_ids = [str(pid) for pid in project_ids]
    outbox_rows = db.execute(
        select(NotificationOutbox.entity_id)
        .where(NotificationOutbox.entity_type == "project")
        .where(NotificationOutbox.entity_id.in_(str_ids))
        .where(NotificationOutbox.status == "FAILED")
    ).all()
    lookups.failed_outbox = {UUID(row[0]) for row in outbox_rows if row[0]}

    return lookups


def _deposit_state_cached(project: Project, lookups: _ProjectLookups) -> str:
    return "PAID" if project.id in lookups.deposit_paid else "PENDING"


def _final_state_cached(project: Project, lookups: _ProjectLookups) -> str:
    if project.id not in lookups.final_paid:
        return "PENDING"
    return "CONFIRMED" if project.id in lookups.confirmed else "AWAITING_CONFIRMATION"


def _compute_attention_flags_cached(project: Project, lookups: _ProjectLookups) -> list[str]:
    """Same logic as _compute_attention_flags but uses pre-fetched lookups (0 queries)."""
    flags = []
    status = project.status

    if status == "DRAFT":
        if project.id not in lookups.deposit_paid:
            flags.append("missing_deposit")
    elif status == "PAID":
        if not project.scheduled_for:
            flags.append("stale_paid_no_schedule")
    elif status == "CERTIFIED":
        if project.id not in lookups.final_paid:
            flags.append("missing_final")
        elif project.id not in lookups.confirmed:
            flags.append("pending_confirmation")

    if project.id in lookups.failed_outbox:
        flags.append("failed_outbox")

    flags.sort(key=lambda f: ATTENTION_PRIORITY.get(f, 99))
    return flags


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
        last_activity_from = as_of - timedelta(days=365)

    as_of_db = _as_db_dt(db, as_of)
    stmt = select(Project).where(Project.updated_at <= as_of_db).order_by(desc(Project.updated_at), desc(Project.id))
    if last_activity_from is not None:
        stmt = stmt.where(Project.updated_at >= _as_db_dt(db, last_activity_from))
    if last_activity_to is not None:
        stmt = stmt.where(Project.updated_at <= _as_db_dt(db, last_activity_to))

    projects = db.execute(stmt).scalars().all()

    # Batch prefetch all related data in 4 queries (instead of N×4)
    all_project_ids = [p.id for p in projects]
    lookups = _prefetch_project_lookups(db, all_project_ids)

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

        # Compute attention flags from most recent project (using batch lookups)
        all_flags: list[str] = []
        for p in projs:
            all_flags.extend(_compute_attention_flags_cached(p, lookups))
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

        dep_state = _deposit_state_cached(latest, lookups)
        fin_state = _final_state_cached(latest, lookups)
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
                # Optional hint for list UI actions (using batch lookups).
                "next_best_action": _compute_next_best_action_cached(projs, lookups),
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


# ---------------------------------------------------------------------------
# Dashboard view model
# ---------------------------------------------------------------------------

STUCK_REASON_MAP: dict[str, str] = {
    "pending_confirmation": "Laukia kliento patvirtinimo",
    "failed_outbox": "Nepavyko išsiųsti pranešimo",
    "missing_deposit": "Reikia įrašyti depozitą",
    "missing_final": "Reikia įrašyti galutinį mokėjimą",
    "stale_paid_no_schedule": "Apmokėta, bet nesuplanuotas vizitas",
}


def _stuck_reason_for_flags(flags: list[str]) -> str:
    """Return single-sentence reason from highest-priority flag."""
    for f in flags:
        if f in STUCK_REASON_MAP:
            return STUCK_REASON_MAP[f]
    return "Reikia dėmesio"


def _urgency_for_flags(flags: list[str]) -> str:
    """Map attention flags to urgency level for UI."""
    if "pending_confirmation" in flags:
        return "high"
    if "failed_outbox" in flags:
        return "medium"
    return "low"


def _count_new_calls(db: Session) -> int:
    """Count call requests with status NEW."""
    try:
        row = db.execute(select(func.count()).select_from(CallRequest).where(CallRequest.status == "NEW")).scalar()
        return int(row) if row is not None else 0
    except Exception:
        return 0


def build_dashboard_view(
    db: Session,
    *,
    settings: Any = None,
    triage_limit: int = 20,
) -> dict[str, Any]:
    """Build dashboard view model: hero stats, triage items, optional ai_summary."""
    customers_data = build_customer_list(db, attention_only=True, limit=triage_limit * 2)

    items = customers_data.get("items", [])
    urgent_count = len(items)

    # Hero stats: aggregate counts from items
    stats = {
        "pending_confirmation": 0,
        "failed_outbox": 0,
        "missing_deposit": 0,
        "new_calls": _count_new_calls(db),
    }
    for item in items:
        flags = item.get("attention_flags") or []
        if "pending_confirmation" in flags:
            stats["pending_confirmation"] += 1
        if "failed_outbox" in flags:
            stats["failed_outbox"] += 1
        if "missing_deposit" in flags:
            stats["missing_deposit"] += 1

    # Triage: first N items with urgency and stuck_reason
    triage: list[dict[str, Any]] = []
    for item in items[:triage_limit]:
        nba = item.get("next_best_action")
        last_proj = item.get("last_project") or {}
        project_id = str(last_proj.get("id", ""))
        triage.append(
            {
                "client_key": item.get("client_key"),
                "contact_masked": item.get("contact_masked") or "-",
                "project_id": project_id,
                "urgency": _urgency_for_flags(item.get("attention_flags") or []),
                "stuck_reason": _stuck_reason_for_flags(item.get("attention_flags") or []),
                "next_best_action": nba,
            }
        )

    ai_summary: str | None = None
    if settings and getattr(settings, "enable_ai_summary", False):
        parts = []
        if stats["missing_deposit"]:
            parts.append(f"{stats['missing_deposit']} klientai laukia depozito")
        if stats["pending_confirmation"]:
            parts.append(f"{stats['pending_confirmation']} – patvirtinimo")
        if stats["failed_outbox"]:
            parts.append(f"{stats['failed_outbox']} – nepavykę pranešimai")
        if stats["new_calls"]:
            parts.append(f"{stats['new_calls']} nauji skambučiai")
        if parts:
            ai_summary = "Rekomenduojama: " + ", ".join(parts) + "."

    return {
        "hero": {"urgent_count": urgent_count, "stats": stats},
        "triage": triage,
        "ai_summary": ai_summary,
        "customers_preview": items[:10],
    }


# ---------------------------------------------------------------------------
# Projects view model (V3, LOCK 1.1 — separate from GET /admin/projects)
# ---------------------------------------------------------------------------

PROJECTS_VIEW_VERSION = "1.0"


def _next_best_action_for_project(project: Project, db: Session) -> dict | None:
    """Next best action for a single project (used by projects view)."""
    status = project.status
    if status == "DRAFT":
        if _deposit_state(project, db) != "PAID":
            return {
                "type": "record_deposit",
                "project_id": str(project.id),
                "label": "Įrašyti depozitą",
            }
    elif status == "PAID":
        return {
            "type": "schedule_visit",
            "project_id": str(project.id),
            "label": "Suplanuoti vizitą",
        }
    elif status == "SCHEDULED":
        return {
            "type": "assign_expert",
            "project_id": str(project.id),
            "label": "Priskirti ekspertą",
        }
    elif status == "PENDING_EXPERT":
        return {
            "type": "certify_project",
            "project_id": str(project.id),
            "label": "Sertifikuoti",
        }
    elif status == "CERTIFIED":
        fs = _final_state(project, db)
        if fs == "PENDING":
            return {
                "type": "record_final",
                "project_id": str(project.id),
                "label": "Įrašyti galutinį mokėjimą",
            }
        if fs == "AWAITING_CONFIRMATION":
            return {
                "type": "resend_confirmation",
                "project_id": str(project.id),
                "label": "Persiųsti patvirtinimą",
            }
    return None


def _encode_projects_view_cursor(as_of: datetime, updated_at: datetime, project_id: str) -> str:
    payload = f"{as_of.isoformat()}|{updated_at.isoformat()}|{project_id}".encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("utf-8")


def _decode_projects_view_cursor(value: str) -> tuple[datetime, datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(value.encode("utf-8")).decode("utf-8")
        as_of_raw, up_raw, pid = raw.split("|", 2)
        return (_parse_iso_dt(as_of_raw), _parse_iso_dt(up_raw), pid)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Invalid cursor") from exc


def build_projects_view(
    db: Session,
    *,
    status: str | None = None,
    attention_only: bool = False,
    limit: int = 50,
    cursor: str | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Build projects view model (V3). LOCK 1.1: separate from GET /admin/projects.

    Returns items with next_best_action, attention_flags, stuck_reason, last_activity,
    client_masked. Cursor bound to as_of (mismatch -> ValueError).
    """
    cursor_as_of = None
    cursor_updated = None
    cursor_pid = None
    if cursor:
        try:
            cursor_as_of, cursor_updated, cursor_pid = _decode_projects_view_cursor(cursor)
        except ValueError as err:
            raise ValueError("Invalid cursor") from err

    if as_of is None:
        as_of = cursor_as_of or datetime.now(timezone.utc)
    else:
        as_of_parsed = _parse_iso_dt(as_of.isoformat()) if hasattr(as_of, "isoformat") else as_of
        if cursor_as_of and as_of_parsed != cursor_as_of:
            raise ValueError("Cursor/as_of mismatch")

    as_of_db = _as_db_dt(db, as_of)
    stmt = select(Project).where(Project.updated_at <= as_of_db).order_by(desc(Project.updated_at), desc(Project.id))
    if status:
        stmt = stmt.where(Project.status == status)

    rows = db.execute(stmt).scalars().all()

    # Batch prefetch all related data in 4 queries (instead of N×5 per project)
    all_pids = [p.id for p in rows]
    lookups = _prefetch_project_lookups(db, all_pids)

    result: list[dict[str, Any]] = []
    for p in rows:
        flags = _compute_attention_flags_cached(p, lookups)
        if attention_only and not flags:
            continue

        ck, _ = derive_client_key(p.client_info)
        ci = p.client_info or {}
        nba = _next_best_action_for_project_cached(p, lookups)

        last_activity = p.updated_at or p.created_at

        result.append(
            {
                "id": str(p.id),
                "status": p.status,
                "scheduled_for": _iso_utc(p.scheduled_for) if p.scheduled_for else None,
                "assigned_contractor_id": str(p.assigned_contractor_id) if p.assigned_contractor_id else None,
                "assigned_expert_id": str(p.assigned_expert_id) if p.assigned_expert_id else None,
                "created_at": _iso_utc(p.created_at),
                "updated_at": _iso_utc(p.updated_at),
                "client_key": ck,
                "client_masked": _contact_masked(ci),
                "attention_flags": flags,
                "stuck_reason": _stuck_reason_for_flags(flags),
                "last_activity": _iso_utc(last_activity),
                "next_best_action": nba,
                "deposit_state": _deposit_state_cached(p, lookups),
                "final_state": _final_state_cached(p, lookups),
                "quote_pending": bool(ci.get("quote_pending")),
            }
        )

    if cursor_updated is not None and cursor_pid:
        filtered = []
        for item in result:
            la_str = item.get("last_activity") or ""
            pid = item.get("id", "")
            la_dt = _parse_iso_dt(la_str) if la_str else datetime.min.replace(tzinfo=timezone.utc)
            if la_dt < cursor_updated or (la_dt == cursor_updated and pid < cursor_pid):
                filtered.append(item)
        result = filtered

    page = result[: limit + 1]
    has_more = len(page) > limit
    page = page[:limit]

    next_cursor = None
    if has_more and page:
        last = page[-1]
        la = last.get("last_activity")
        pid = last.get("id", "")
        if la and pid:
            la_dt = _parse_iso_dt(la)
            next_cursor = _encode_projects_view_cursor(as_of, la_dt, pid)

    return {
        "items": page,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "as_of": _parse_iso_dt(as_of.isoformat()).isoformat(),
        "view_version": PROJECTS_VIEW_VERSION,
    }


def build_projects_mini_triage(db: Session, *, limit: int = 20) -> list[dict[str, Any]]:
    """Build mini triage for projects (laukiantys schedule/expert). LOCK 1.6.

    Returns triage cards with primary_action (label, action_key, payload).
    """
    stmt = (
        select(Project)
        .where(Project.status.in_(["PAID", "SCHEDULED"]))
        .order_by(desc(Project.updated_at))
        .limit(limit * 2)
    )
    rows = db.execute(stmt).scalars().all()

    # Batch prefetch
    lookups = _prefetch_project_lookups(db, [p.id for p in rows])

    triage: list[dict[str, Any]] = []
    for p in rows:
        nba = _next_best_action_for_project_cached(p, lookups)
        if not nba:
            continue
        flags = _compute_attention_flags_cached(p, lookups)
        ck, _ = derive_client_key(p.client_info)
        ci = p.client_info or {}

        primary_action = {
            "label": nba.get("label", nba.get("type", "")),
            "action_key": nba.get("type", ""),
            "payload": {"project_id": str(p.id), "client_key": ck},
        }

        triage.append(
            {
                "project_id": str(p.id),
                "client_key": ck,
                "contact_masked": _contact_masked(ci),
                "urgency": _urgency_for_flags(flags),
                "stuck_reason": _stuck_reason_for_flags(flags),
                "primary_action": primary_action,
            }
        )
        if len(triage) >= limit:
            break

    return triage


# ---------------------------------------------------------------------------
# Finance view model (Diena 4 — laukiantys mokėjimai)
# ---------------------------------------------------------------------------

FINANCE_VIEW_VERSION = "1.0"


def build_finance_mini_triage(db: Session, *, limit: int = 20) -> list[dict[str, Any]]:
    """Build mini triage for finance: projects needing deposit (DRAFT) or final (CERTIFIED).

    Returns triage cards with primary_action for quick payment.
    """
    # DRAFT without deposit, or CERTIFIED without final
    stmt = (
        select(Project)
        .where(Project.status.in_(["DRAFT", "CERTIFIED"]))
        .order_by(desc(Project.updated_at))
        .limit(limit * 2)
    )
    rows = db.execute(stmt).scalars().all()

    triage: list[dict[str, Any]] = []
    for p in rows:
        nba = None
        if p.status == "DRAFT" and _deposit_state(p, db) != "PAID":
            nba = {"type": "record_deposit", "label": "Įrašyti įnašą", "project_id": str(p.id)}
        elif p.status == "CERTIFIED" and _final_state(p, db) == "PENDING":
            nba = {"type": "record_final", "label": "Įrašyti galutinį mokėjimą", "project_id": str(p.id)}
        if not nba:
            continue

        ck, _ = derive_client_key(p.client_info)
        ci = p.client_info or {}
        triage.append(
            {
                "project_id": str(p.id),
                "client_key": ck,
                "contact_masked": _contact_masked(ci),
                "urgency": "high" if p.status == "DRAFT" else "medium",
                "stuck_reason": STUCK_REASON_MAP.get(
                    "missing_deposit" if p.status == "DRAFT" else "missing_final",
                    "Reikia mokėjimo",
                ),
                "primary_action": {
                    "label": nba.get("label", ""),
                    "action_key": nba.get("type", ""),
                    "payload": {"project_id": str(p.id), "client_key": ck},
                },
            }
        )
        if len(triage) >= limit:
            break

    return triage


def build_finance_view(db: Session, *, settings: Any = None) -> dict[str, Any]:
    """Build finance view model: mini_triage, ai_summary, manual_payments_count."""
    triage = build_finance_mini_triage(db, limit=20)

    # Count manual payments (for AI summary)
    manual_count_stmt = (
        select(func.count(AuditLog.id))
        .where(AuditLog.action == "PAYMENT_RECORDED_MANUAL")
        .where(AuditLog.timestamp >= _as_db_dt(db, datetime.now(timezone.utc) - timedelta(days=7)))
    )
    manual_payments_7d = db.execute(manual_count_stmt).scalar() or 0

    ai_summary: str | None = None
    if settings and getattr(settings, "enable_ai_summary", False):
        parts = []
        if triage:
            parts.append(f"{len(triage)} laukiantys mokėjimai")
        if manual_payments_7d:
            parts.append(f"{manual_payments_7d} rankiniai per 7d")
        if parts:
            ai_summary = "Rekomenduojama: " + ", ".join(parts) + "."

    return {
        "items": triage,
        "manual_payments_count_7d": manual_payments_7d,
        "ai_summary": ai_summary,
        "view_version": FINANCE_VIEW_VERSION,
    }


# ---------------------------------------------------------------------------
# AI view model (Diena 4 — low confidence, attention)
# ---------------------------------------------------------------------------

AI_VIEW_VERSION = "1.0"
LOW_CONFIDENCE_THRESHOLD = 0.5


def build_ai_view(db: Session, *, settings: Any = None) -> dict[str, Any]:
    """Build AI view model: low_confidence_count, attention items, ai_summary."""
    since = _as_db_dt(db, datetime.now(timezone.utc) - timedelta(hours=24))
    stmt = (
        select(AuditLog)
        .where(AuditLog.entity_type == "ai")
        .where(AuditLog.action == "AI_RUN")
        .where(AuditLog.timestamp >= since)
        .order_by(desc(AuditLog.timestamp))
        .limit(200)
    )
    rows = db.execute(stmt).scalars().all()

    low_confidence: list[dict[str, Any]] = []
    for log in rows:
        nv = log.new_value if hasattr(log, "new_value") and log.new_value else None
        if not isinstance(nv, dict):
            continue
        conf = nv.get("confidence")
        if conf is None:
            continue
        try:
            c = float(conf)
        except (TypeError, ValueError):
            continue
        if c < LOW_CONFIDENCE_THRESHOLD:
            low_confidence.append(
                {
                    "entity_id": str(log.entity_id) if log.entity_id else "",
                    "scope": log.entity_id or "ai",
                    "confidence": round(c, 2),
                    "intent": nv.get("intent", ""),
                    "timestamp": _iso_utc(log.timestamp) if log.timestamp else None,
                }
            )

    low_count = len(low_confidence)

    ai_summary: str | None = None
    if settings and getattr(settings, "enable_ai_summary", False) and low_count > 0:
        ai_summary = f"Patikrinti {low_count} klaid" + ("as" if low_count == 1 else "ų")

    return {
        "low_confidence_count": low_count,
        "attention_items": low_confidence[:10],
        "ai_summary": ai_summary,
        "view_version": AI_VIEW_VERSION,
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


def _compute_next_best_action_cached(projects: list[Project], lookups: _ProjectLookups) -> dict | None:
    """Same as _compute_next_best_action but uses pre-fetched lookups (0 queries)."""
    for p in projects:
        status = p.status
        if status == "DRAFT":
            if _deposit_state_cached(p, lookups) != "PAID":
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
            fs = _final_state_cached(p, lookups)
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


def _next_best_action_for_project_cached(project: Project, lookups: _ProjectLookups) -> dict | None:
    """Same as _next_best_action_for_project but uses pre-fetched lookups (0 queries)."""
    status = project.status
    if status == "DRAFT":
        if _deposit_state_cached(project, lookups) != "PAID":
            return {
                "type": "record_deposit",
                "project_id": str(project.id),
                "label": "Įrašyti depozitą",
            }
    elif status == "PAID":
        return {
            "type": "schedule_visit",
            "project_id": str(project.id),
            "label": "Suplanuoti vizitą",
        }
    elif status == "SCHEDULED":
        return {
            "type": "assign_expert",
            "project_id": str(project.id),
            "label": "Priskirti ekspertą",
        }
    elif status == "PENDING_EXPERT":
        return {
            "type": "certify_project",
            "project_id": str(project.id),
            "label": "Sertifikuoti",
        }
    elif status == "CERTIFIED":
        fs = _final_state_cached(project, lookups)
        if fs == "PENDING":
            return {
                "type": "record_final",
                "project_id": str(project.id),
                "label": "Įrašyti galutinį mokėjimą",
            }
        if fs == "AWAITING_CONFIRMATION":
            return {
                "type": "resend_confirmation",
                "project_id": str(project.id),
                "label": "Persiųsti patvirtinimą",
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

    # Batch prefetch for all matching projects
    matching_ids = [p.id for p in matching]
    lookups = _prefetch_project_lookups(db, matching_ids)

    # Build project list with actions
    proj_list = []
    for p in matching:
        proj_list.append(
            {
                "id": str(p.id),
                "status": p.status,
                "created_at": _iso_utc(p.created_at),
                "updated_at": _iso_utc(p.updated_at),
                "deposit_state": _deposit_state_cached(p, lookups),
                "final_state": _final_state_cached(p, lookups),
                "actions_available": _actions_available(p, db),
                "area_m2": p.area_m2,
            }
        )

    # Attention flags (using batch lookups)
    all_flags: list[str] = []
    for p in matching:
        all_flags.extend(_compute_attention_flags_cached(p, lookups))
    seen = set()
    unique_flags = []
    for f in all_flags:
        if f not in seen:
            seen.add(f)
            unique_flags.append(f)
    unique_flags.sort(key=lambda f: ATTENTION_PRIORITY.get(f, 99))

    # Summary — batch query for total paid (1 query instead of N)
    total_paid_row = db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0))
        .where(Payment.project_id.in_(matching_ids))
        .where(Payment.status == "SUCCEEDED")
    ).scalar()
    total_paid = float(total_paid_row or 0)

    # Feature flags
    feature_flags = {}
    if settings:
        feature_flags = {
            "finance_ledger": getattr(settings, "enable_finance_ledger", False),
            "finance_ai_ingest": getattr(settings, "enable_finance_ai_ingest", False),
            "ai_pricing": getattr(settings, "enable_ai_pricing", False),
        }

    return {
        "client_key": client_key,
        "client_info": {
            "display_name": _display_name(client_info_sample),
            "contact_masked": _contact_masked(client_info_sample),
        },
        "projects": proj_list,
        "next_best_action": _compute_next_best_action_cached(matching, lookups),
        "attention_flags": unique_flags,
        "summary": {
            "total_projects": len(matching),
            "total_paid": total_paid,
        },
        "feature_flags": feature_flags,
    }
