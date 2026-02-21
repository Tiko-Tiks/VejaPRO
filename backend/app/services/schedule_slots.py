"""Shared schedule slot finder — extracted from twilio_voice.py for reuse."""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.project import Appointment, User

VILNIUS_TZ = ZoneInfo("Europe/Vilnius")
CANDIDATE_HOURS = [10, 13, 16]
OPEN_FROM = time(9, 0)
OPEN_TO = time(18, 0)

DAYS_LT = [
    "pirmadienis",
    "antradienis",
    "trečiadienis",
    "ketvirtadienis",
    "penktadienis",
    "šeštadienis",
    "sekmadienis",
]


def pick_resource_id(db: Session) -> uuid.UUID | None:
    """Return configured default resource or auto-pick earliest active operator."""
    settings = get_settings()
    if settings.schedule_default_resource_id:
        try:
            return uuid.UUID(settings.schedule_default_resource_id)
        except ValueError:
            return None

    row = (
        db.execute(
            select(User.id)
            .where(
                and_(
                    User.is_active.is_(True),
                    User.role.in_(["ADMIN", "SUBCONTRACTOR"]),
                )
            )
            .order_by(User.created_at.asc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    return row


def find_available_slots(
    db: Session,
    resource_id: uuid.UUID,
    duration_min: int = 60,
    count: int = 10,
    horizon_days: int = 14,
) -> list[dict]:
    """Return up to `count` free slots within `horizon_days`."""
    now_local = datetime.now(VILNIUS_TZ)
    duration = timedelta(minutes=max(15, duration_min))
    slots: list[dict] = []

    for day_offset in range(0, horizon_days):
        d = now_local.date() + timedelta(days=day_offset)
        if d.weekday() == 6:  # skip Sundays
            continue

        for hour in CANDIDATE_HOURS:
            start_local = datetime.combine(d, time(hour, 0), tzinfo=VILNIUS_TZ)
            end_local = start_local + duration

            if start_local.time() < OPEN_FROM or end_local.time() > OPEN_TO:
                continue
            if start_local < now_local + timedelta(minutes=30):
                continue

            start_utc = start_local.astimezone(timezone.utc)
            end_utc = end_local.astimezone(timezone.utc)

            conflict = (
                db.execute(
                    select(Appointment.id).where(
                        Appointment.resource_id == resource_id,
                        Appointment.status.in_(["HELD", "CONFIRMED"]),
                        Appointment.starts_at < end_utc,
                        Appointment.ends_at > start_utc,
                    )
                )
                .scalars()
                .first()
            )
            if conflict:
                continue

            day_name = DAYS_LT[d.weekday()]
            label = f"{d.isoformat()}, {day_name} {start_local.strftime('%H:%M')}–{end_local.strftime('%H:%M')}"

            slots.append(
                {
                    "starts_at": start_utc.isoformat(),
                    "ends_at": end_utc.isoformat(),
                    "label": label,
                }
            )
            if len(slots) >= count:
                return slots

    return slots
