"""
Tests for recurring jobs — expire_held_appointments.

Covers:
  - Expired HELD appointments become CANCELLED with HOLD_EXPIRED reason
  - Non-expired HELD appointments stay HELD
  - CONFIRMED appointments are not affected
  - Expired conversation locks are cleaned up
  - Row version is incremented on expiry
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest


def _get_db():
    from app.core.dependencies import SessionLocal

    if SessionLocal is None:
        pytest.skip("DATABASE_URL is not configured")
    return SessionLocal()


def _now_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _create_call_request(db):
    """Create a minimal CallRequest to satisfy FK for Appointment."""
    from app.models.project import CallRequest

    cr_id = uuid.uuid4()
    cr = CallRequest(
        id=cr_id,
        name="Test Client",
        phone="+37060000000",
        status="NEW",
    )
    db.add(cr)
    db.flush()
    return cr_id


def test_expire_held_appointment():
    """HELD appointment past hold_expires_at should become CANCELLED."""
    from app.models.project import Appointment
    from app.services.recurring_jobs import expire_held_appointments

    db = _get_db()
    try:
        cr_id = _create_call_request(db)
        now = _now_naive()
        appt_id = uuid.uuid4()

        appt = Appointment(
            id=appt_id,
            call_request_id=cr_id,
            visit_type="PRIMARY",
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=1, hours=1),
            status="HELD",
            lock_level=0,
            hold_expires_at=now - timedelta(minutes=5),  # expired
            weather_class="MIXED",
            row_version=1,
        )
        db.add(appt)
        db.commit()

        count = expire_held_appointments(db)
        db.commit()

        assert count == 1

        row = db.query(Appointment).filter(Appointment.id == appt_id).first()
        assert row.status == "CANCELLED"
        assert row.cancel_reason == "HOLD_EXPIRED"
        assert row.hold_expires_at is None
        assert row.row_version == 2
    finally:
        db.close()


def test_non_expired_held_stays():
    """HELD appointment with future hold_expires_at should remain HELD."""
    from app.models.project import Appointment
    from app.services.recurring_jobs import expire_held_appointments

    db = _get_db()
    try:
        cr_id = _create_call_request(db)
        now = _now_naive()
        appt_id = uuid.uuid4()

        appt = Appointment(
            id=appt_id,
            call_request_id=cr_id,
            visit_type="PRIMARY",
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=1, hours=1),
            status="HELD",
            lock_level=0,
            hold_expires_at=now + timedelta(hours=1),  # not expired
            weather_class="MIXED",
            row_version=1,
        )
        db.add(appt)
        db.commit()

        count = expire_held_appointments(db)
        db.commit()

        assert count == 0

        row = db.query(Appointment).filter(Appointment.id == appt_id).first()
        assert row.status == "HELD"
        assert row.row_version == 1
    finally:
        db.close()


def test_confirmed_appointment_not_affected():
    """CONFIRMED appointments should not be touched by expiry."""
    from app.models.project import Appointment
    from app.services.recurring_jobs import expire_held_appointments

    db = _get_db()
    try:
        cr_id = _create_call_request(db)
        now = _now_naive()
        appt_id = uuid.uuid4()

        appt = Appointment(
            id=appt_id,
            call_request_id=cr_id,
            visit_type="PRIMARY",
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=1, hours=1),
            status="CONFIRMED",
            lock_level=0,
            hold_expires_at=None,
            weather_class="MIXED",
            row_version=1,
        )
        db.add(appt)
        db.commit()

        count = expire_held_appointments(db)
        db.commit()

        assert count == 0

        row = db.query(Appointment).filter(Appointment.id == appt_id).first()
        assert row.status == "CONFIRMED"
    finally:
        db.close()


def test_expired_conversation_lock_cleaned():
    """Expired ConversationLock should be deleted."""
    from app.models.project import Appointment, ConversationLock
    from app.services.recurring_jobs import expire_held_appointments

    db = _get_db()
    try:
        cr_id = _create_call_request(db)
        now = _now_naive()
        appt_id = uuid.uuid4()

        # Create a HELD appointment (needed as FK for ConversationLock)
        appt = Appointment(
            id=appt_id,
            call_request_id=cr_id,
            visit_type="PRIMARY",
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=1, hours=1),
            status="HELD",
            lock_level=0,
            hold_expires_at=now - timedelta(minutes=5),
            weather_class="MIXED",
            row_version=1,
        )
        db.add(appt)
        db.flush()

        lock_id = uuid.uuid4()
        lock = ConversationLock(
            id=lock_id,
            channel="whatsapp",
            conversation_id="test-conv-" + str(uuid.uuid4()),
            appointment_id=appt_id,
            visit_type="PRIMARY",
            hold_expires_at=now - timedelta(minutes=5),  # expired
        )
        db.add(lock)
        db.commit()

        expire_held_appointments(db)
        db.commit()

        # Lock should be deleted
        remaining = db.query(ConversationLock).filter(ConversationLock.id == lock_id).first()
        assert remaining is None
    finally:
        db.close()


def test_multiple_expired_appointments():
    """Multiple expired HELD appointments should all be cancelled."""
    from app.models.project import Appointment
    from app.services.recurring_jobs import expire_held_appointments

    db = _get_db()
    try:
        now = _now_naive()
        ids = []

        for i in range(3):
            cr_id = _create_call_request(db)
            appt_id = uuid.uuid4()
            ids.append(appt_id)

            appt = Appointment(
                id=appt_id,
                call_request_id=cr_id,
                visit_type="PRIMARY",
                starts_at=now + timedelta(days=1),
                ends_at=now + timedelta(days=1, hours=1),
                status="HELD",
                lock_level=0,
                hold_expires_at=now - timedelta(minutes=i + 1),
                weather_class="MIXED",
                row_version=1,
            )
            db.add(appt)
        db.commit()

        count = expire_held_appointments(db)
        db.commit()

        assert count == 3

        for appt_id in ids:
            row = db.query(Appointment).filter(Appointment.id == appt_id).first()
            assert row.status == "CANCELLED"
            assert row.cancel_reason == "HOLD_EXPIRED"
    finally:
        db.close()
