from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import SessionLocal
from app.models.project import Appointment, ConversationLock
from app.services.notification_outbox import process_notification_outbox_once

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    # SQLite (used in CI/tests) stores timezone-aware datetimes as naive values.
    # Use a naive UTC "now" for SQLite to avoid naive/aware comparison crashes.
    settings = get_settings()
    if (settings.database_url or "").startswith("sqlite"):
        # datetime.utcnow() is deprecated; keep the same naive-UTC semantics.
        return datetime.now(timezone.utc).replace(tzinfo=None)
    return datetime.now(timezone.utc)


def expire_held_appointments(db: Session) -> int:
    """
    Idempotent cleanup:
    - HELD + hold_expires_at < now => CANCELLED (HOLD_EXPIRED), hold_expires_at=NULL, row_version++
    - deletes expired conversation_locks
    No audit required per spec.
    """
    now = _now_utc()

    expired = (
        db.execute(
            select(Appointment).where(
                Appointment.status == "HELD",
                Appointment.hold_expires_at.is_not(None),
                Appointment.hold_expires_at < now,
            )
        )
        .scalars()
        .all()
    )

    count = 0
    for appt in expired:
        appt.status = "CANCELLED"
        appt.cancel_reason = "HOLD_EXPIRED"
        appt.hold_expires_at = None
        appt.row_version = int(appt.row_version or 1) + 1
        count += 1

    # Best-effort cleanup (covers both expired holds and any stale locks).
    db.execute(delete(ConversationLock).where(ConversationLock.hold_expires_at < now))
    return count


async def _hold_expiry_loop(*, interval_seconds: int) -> None:
    # Backoff on errors to avoid tight loops.
    error_sleep = max(10, min(60, interval_seconds))
    while True:
        try:
            settings = get_settings()
            if not settings.enable_recurring_jobs:
                await asyncio.sleep(interval_seconds)
                continue
            if not settings.enable_schedule_engine:
                await asyncio.sleep(interval_seconds)
                continue
            if SessionLocal is None:
                await asyncio.sleep(interval_seconds)
                continue

            db = SessionLocal()
            try:
                expired_count = expire_held_appointments(db)
                if expired_count:
                    logger.info("Expired HELD appointments: %s", expired_count)
                db.commit()
            finally:
                db.close()
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Hold expiry worker error")
            await asyncio.sleep(error_sleep)


def start_hold_expiry_worker() -> asyncio.Task | None:
    """
    Starts an in-process cleanup loop. Safe to call multiple times in the same process;
    callers should keep their own reference if they need explicit cancellation.
    """
    settings = get_settings()
    interval = getattr(settings, "schedule_hold_expiry_interval_seconds", 60) or 60
    interval = int(max(15, min(300, interval)))
    return asyncio.create_task(_hold_expiry_loop(interval_seconds=interval))


async def _notification_outbox_loop(
    *, interval_seconds: int, batch_size: int, max_attempts: int
) -> None:
    error_sleep = max(10, min(60, interval_seconds))
    while True:
        try:
            settings = get_settings()
            if not settings.enable_recurring_jobs:
                await asyncio.sleep(interval_seconds)
                continue
            if not getattr(settings, "enable_notification_outbox", True):
                await asyncio.sleep(interval_seconds)
                continue
            if SessionLocal is None:
                await asyncio.sleep(interval_seconds)
                continue

            db = SessionLocal()
            try:
                process_notification_outbox_once(
                    db,
                    batch_size=batch_size,
                    max_attempts=max_attempts,
                )
                db.commit()
            finally:
                db.close()
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Notification outbox worker error")
            await asyncio.sleep(error_sleep)


def start_notification_outbox_worker() -> asyncio.Task | None:
    settings = get_settings()
    interval = int(
        max(
            5,
            min(
                300,
                int(
                    getattr(settings, "notification_worker_interval_seconds", 30) or 30
                ),
            ),
        )
    )
    batch_size = int(
        max(
            1,
            min(
                200, int(getattr(settings, "notification_worker_batch_size", 50) or 50)
            ),
        )
    )
    max_attempts = int(
        max(
            1,
            min(20, int(getattr(settings, "notification_worker_max_attempts", 5) or 5)),
        )
    )
    return asyncio.create_task(
        _notification_outbox_loop(
            interval_seconds=interval,
            batch_size=batch_size,
            max_attempts=max_attempts,
        )
    )
