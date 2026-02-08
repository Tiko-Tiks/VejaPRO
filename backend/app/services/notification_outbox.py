from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.project import NotificationOutbox
from app.services.sms_service import send_sms

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    # SQLite (used in CI/tests) stores timezone-aware datetimes as naive values.
    # Use a naive UTC "now" for SQLite to avoid naive/aware comparison crashes.
    settings = get_settings()
    if (settings.database_url or "").startswith("sqlite"):
        # datetime.utcnow() is deprecated; keep the same naive-UTC semantics.
        return datetime.now(timezone.utc).replace(tzinfo=None)
    return datetime.now(timezone.utc)


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _dedupe_key(*, channel: str, template_key: str, entity_type: str, entity_id: str, payload_json: Any) -> str:
    raw = _canonical_json(
        {
            "channel": channel,
            "template_key": template_key,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload_json,
        }
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    # Keep it human-readable and stable, but bounded.
    return f"{channel}:{template_key}:{entity_type}:{entity_id}:{digest[:16]}"


def enqueue_notification(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    channel: str,
    template_key: str,
    payload_json: dict[str, Any],
) -> bool:
    """
    Inserts a notification request into the outbox.
    Best-effort idempotency via dedupe_key.
    """
    dedupe = _dedupe_key(
        channel=channel,
        template_key=template_key,
        entity_type=entity_type,
        entity_id=entity_id,
        payload_json=payload_json,
    )

    values = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "channel": channel,
        "template_key": template_key,
        "payload_json": payload_json,
        "dedupe_key": dedupe,
        "status": "PENDING",
        "attempt_count": 0,
        "next_attempt_at": _now_utc(),
    }

    # Must not break the caller transaction: use ON CONFLICT DO NOTHING semantics where possible.
    dialect = getattr(getattr(db, "bind", None), "dialect", None)
    dialect_name = getattr(dialect, "name", "") or ""
    table = NotificationOutbox.__table__

    if dialect_name == "postgresql":
        stmt = pg_insert(table).values(**values).on_conflict_do_nothing(index_elements=["dedupe_key"])
        result = db.execute(stmt)
        return bool(result.rowcount)
    if dialect_name == "sqlite":
        stmt = sqlite_insert(table).values(**values).prefix_with("OR IGNORE")
        result = db.execute(stmt)
        return bool(result.rowcount)

    # Fallback: check then insert (may still race).
    existing = db.execute(
        select(NotificationOutbox.id).where(NotificationOutbox.dedupe_key == dedupe)
    ).scalar_one_or_none()
    if existing is not None:
        return False
    db.execute(insert(table).values(**values))
    return True


def _compute_backoff(attempt_count: int) -> timedelta:
    # 1m, 2m, 4m, 8m, ... capped to 60m
    seconds = 60 * (2 ** max(0, attempt_count - 1))
    seconds = max(60, min(3600, seconds))
    return timedelta(seconds=seconds)


def process_notification_outbox_once(
    db: Session,
    *,
    batch_size: int = 50,
    max_attempts: int = 5,
) -> int:
    """
    Processes due notifications.
    Returns number of successfully SENT items.
    """
    now = _now_utc()
    settings = get_settings()

    due = (
        db.execute(
            select(NotificationOutbox)
            .where(
                NotificationOutbox.status.in_(["PENDING", "RETRY"]),
                NotificationOutbox.next_attempt_at <= now,
            )
            .order_by(NotificationOutbox.next_attempt_at.asc())
            .limit(int(max(1, batch_size)))
        )
        .scalars()
        .all()
    )

    sent = 0
    for row in due:
        row.attempt_count = int(row.attempt_count or 0) + 1

        try:
            if row.channel != "sms":
                raise RuntimeError(f"Nepalaikomas kanalas: {row.channel}")

            if not settings.enable_twilio:
                raise RuntimeError("Twilio isjungtas")

            payload = row.payload_json or {}
            to_number = str(payload.get("to_number") or "").strip()
            body = str(payload.get("body") or "").strip()
            if not to_number or not body:
                raise RuntimeError("Truksta SMS lauku (to_number/body)")

            # Side-effect: Twilio send
            send_sms(to_number, body)

            row.status = "SENT"
            row.sent_at = now
            row.last_error = None
            sent += 1
        except Exception as exc:
            row.last_error = str(exc)
            if int(row.attempt_count or 0) >= int(max_attempts):
                row.status = "FAILED"
                row.next_attempt_at = now + timedelta(days=365)
            else:
                row.status = "RETRY"
                row.next_attempt_at = now + _compute_backoff(int(row.attempt_count or 0))

    if due and sent:
        logger.info("Notification outbox processed: sent=%s total=%s", sent, len(due))
    return sent
