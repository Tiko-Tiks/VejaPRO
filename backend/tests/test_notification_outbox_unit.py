"""
Tests for notification outbox service — enqueue, process, retry, backoff, channels.

Covers:
  - Idempotent enqueue via dedupe_key
  - Different payloads create separate records
  - process_notification_outbox_once with mocked channels
  - Retry logic and exponential backoff
  - FAILED status after max attempts
  - Channel routing (sms, email, whatsapp_ping, unknown)
  - ICS calendar invite builder
  - WhatsApp stub behavior
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════


def _get_db():
    from app.core.dependencies import SessionLocal

    if SessionLocal is None:
        pytest.skip("DATABASE_URL is not configured")
    return SessionLocal()


def _enqueue(db, **overrides):
    from app.services.notification_outbox import enqueue_notification

    defaults = {
        "entity_type": "test",
        "entity_id": str(uuid.uuid4()),
        "channel": "sms",
        "template_key": "TEST",
        "payload_json": {"to_number": "+37060000000", "body": "Test"},
    }
    defaults.update(overrides)
    return enqueue_notification(db, **defaults)


# ═══════════════════════════════════════════════════════════════
# Enqueue tests
# ═══════════════════════════════════════════════════════════════


def test_notification_outbox_dedupe_key_idempotent():
    """Enqueue with identical parameters should insert only once."""
    from app.models.project import NotificationOutbox

    db = _get_db()
    try:
        eid = str(uuid.uuid4())
        created1 = _enqueue(db, entity_id=eid)
        created2 = _enqueue(db, entity_id=eid)
        db.commit()

        assert created1 is True
        assert created2 is False

        count = (
            db.query(NotificationOutbox)
            .filter(NotificationOutbox.entity_id == eid)
            .count()
        )
        assert count == 1
    finally:
        db.close()


def test_different_payloads_create_separate_records():
    """Different payload_json should produce different dedupe_keys."""
    from app.models.project import NotificationOutbox

    db = _get_db()
    try:
        eid = str(uuid.uuid4())
        created1 = _enqueue(
            db,
            entity_id=eid,
            payload_json={"to_number": "+37060000001", "body": "A"},
        )
        created2 = _enqueue(
            db,
            entity_id=eid,
            payload_json={"to_number": "+37060000002", "body": "B"},
        )
        db.commit()

        assert created1 is True
        assert created2 is True

        count = (
            db.query(NotificationOutbox)
            .filter(NotificationOutbox.entity_id == eid)
            .count()
        )
        assert count == 2
    finally:
        db.close()


def test_different_channels_create_separate_records():
    """Same entity but different channels should create separate records."""
    from app.models.project import NotificationOutbox

    db = _get_db()
    try:
        eid = str(uuid.uuid4())
        created1 = _enqueue(db, entity_id=eid, channel="sms")
        created2 = _enqueue(db, entity_id=eid, channel="email",
                            payload_json={"to": "a@b.com", "subject": "X", "body_text": "Y"})
        db.commit()

        assert created1 is True
        assert created2 is True

        count = (
            db.query(NotificationOutbox)
            .filter(NotificationOutbox.entity_id == eid)
            .count()
        )
        assert count == 2
    finally:
        db.close()


def test_enqueue_sets_pending_status():
    """Enqueued notification should have PENDING status and attempt_count 0."""
    from app.models.project import NotificationOutbox

    db = _get_db()
    try:
        eid = str(uuid.uuid4())
        _enqueue(db, entity_id=eid)
        db.commit()

        row = (
            db.query(NotificationOutbox)
            .filter(NotificationOutbox.entity_id == eid)
            .first()
        )
        assert row is not None
        assert row.status == "PENDING"
        assert row.attempt_count == 0
        assert row.next_attempt_at is not None
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# Process tests (with mocked send)
# ═══════════════════════════════════════════════════════════════


def test_process_sms_success():
    """Processing a PENDING SMS notification should call send_sms and set SENT."""
    from app.models.project import NotificationOutbox
    from app.services.notification_outbox import process_notification_outbox_once

    db = _get_db()
    try:
        # Clean up any leftover PENDING/RETRY rows from prior tests
        db.query(NotificationOutbox).filter(
            NotificationOutbox.status.in_(["PENDING", "RETRY"])
        ).delete(synchronize_session="fetch")
        db.commit()

        eid = str(uuid.uuid4())
        _enqueue(
            db,
            entity_id=eid,
            channel="sms",
            template_key="TEST_SMS",
            payload_json={"to_number": "+37060000000", "body": "Hello"},
        )
        db.commit()

        with patch("app.services.notification_outbox.send_sms") as mock_sms, \
             patch("app.services.notification_outbox.get_settings") as mock_settings:
            s = MagicMock()
            s.enable_twilio = True
            s.database_url = "sqlite:///test"
            mock_settings.return_value = s

            sent = process_notification_outbox_once(db, batch_size=10, max_attempts=5)
            db.commit()

        assert sent == 1
        mock_sms.assert_called_once_with("+37060000000", "Hello")

        row = (
            db.query(NotificationOutbox)
            .filter(NotificationOutbox.entity_id == eid)
            .first()
        )
        assert row.status == "SENT"
        assert row.sent_at is not None
        assert row.attempt_count == 1
    finally:
        db.close()


def test_process_sms_twilio_disabled_retries():
    """SMS notification with Twilio disabled should go to RETRY."""
    from app.models.project import NotificationOutbox
    from app.services.notification_outbox import process_notification_outbox_once

    db = _get_db()
    try:
        db.query(NotificationOutbox).filter(
            NotificationOutbox.status.in_(["PENDING", "RETRY"])
        ).delete(synchronize_session="fetch")
        db.commit()

        eid = str(uuid.uuid4())
        _enqueue(
            db,
            entity_id=eid,
            channel="sms",
            template_key="TEST_SMS_FAIL",
            payload_json={"to_number": "+37060000000", "body": "Hello"},
        )
        db.commit()

        with patch("app.services.notification_outbox.get_settings") as mock_settings:
            s = MagicMock()
            s.enable_twilio = False
            s.database_url = "sqlite:///test"
            mock_settings.return_value = s

            sent = process_notification_outbox_once(db, batch_size=10, max_attempts=5)
            db.commit()

        assert sent == 0

        row = (
            db.query(NotificationOutbox)
            .filter(NotificationOutbox.entity_id == eid)
            .first()
        )
        assert row.status == "RETRY"
        assert row.attempt_count == 1
        assert "Twilio" in (row.last_error or "")
    finally:
        db.close()


def test_process_exceeds_max_attempts_fails():
    """After max_attempts, notification should be marked as FAILED."""
    from app.models.project import NotificationOutbox
    from app.services.notification_outbox import process_notification_outbox_once

    db = _get_db()
    try:
        db.query(NotificationOutbox).filter(
            NotificationOutbox.status.in_(["PENDING", "RETRY"])
        ).delete(synchronize_session="fetch")
        db.commit()

        eid = str(uuid.uuid4())
        _enqueue(
            db,
            entity_id=eid,
            channel="sms",
            template_key="TEST_MAX_FAIL",
            payload_json={"to_number": "+37060000000", "body": "Hello"},
        )
        db.commit()

        # Set attempt_count to max_attempts - 1 so next attempt hits the limit
        row = (
            db.query(NotificationOutbox)
            .filter(NotificationOutbox.entity_id == eid)
            .first()
        )
        row.attempt_count = 4  # next attempt will be 5 (= max_attempts)
        row.status = "RETRY"
        db.commit()

        with patch("app.services.notification_outbox.get_settings") as mock_settings:
            s = MagicMock()
            s.enable_twilio = False
            s.database_url = "sqlite:///test"
            mock_settings.return_value = s

            sent = process_notification_outbox_once(db, batch_size=10, max_attempts=5)
            db.commit()

        assert sent == 0

        row = (
            db.query(NotificationOutbox)
            .filter(NotificationOutbox.entity_id == eid)
            .first()
        )
        assert row.status == "FAILED"
        assert row.attempt_count == 5
    finally:
        db.close()


def test_process_unknown_channel_fails():
    """Unknown channel should cause error and RETRY."""
    from app.models.project import NotificationOutbox
    from app.services.notification_outbox import process_notification_outbox_once

    db = _get_db()
    try:
        db.query(NotificationOutbox).filter(
            NotificationOutbox.status.in_(["PENDING", "RETRY"])
        ).delete(synchronize_session="fetch")
        db.commit()

        eid = str(uuid.uuid4())
        _enqueue(
            db,
            entity_id=eid,
            channel="pigeon",
            template_key="TEST_PIGEON",
            payload_json={"destination": "park"},
        )
        db.commit()

        with patch("app.services.notification_outbox.get_settings") as mock_settings:
            s = MagicMock()
            s.database_url = "sqlite:///test"
            mock_settings.return_value = s

            sent = process_notification_outbox_once(db, batch_size=10, max_attempts=5)
            db.commit()

        assert sent == 0

        row = (
            db.query(NotificationOutbox)
            .filter(NotificationOutbox.entity_id == eid)
            .first()
        )
        assert row.status == "RETRY"
        assert "Nepalaikomas" in (row.last_error or "")
    finally:
        db.close()


def test_process_skips_future_notifications():
    """Notifications with next_attempt_at in the future should not be processed."""
    from app.models.project import NotificationOutbox
    from app.services.notification_outbox import process_notification_outbox_once

    db = _get_db()
    try:
        db.query(NotificationOutbox).filter(
            NotificationOutbox.status.in_(["PENDING", "RETRY"])
        ).delete(synchronize_session="fetch")
        db.commit()

        eid = str(uuid.uuid4())
        _enqueue(
            db,
            entity_id=eid,
            channel="sms",
            template_key="TEST_FUTURE",
            payload_json={"to_number": "+37060000000", "body": "Future"},
        )
        db.commit()

        # Push next_attempt_at to the future
        row = (
            db.query(NotificationOutbox)
            .filter(NotificationOutbox.entity_id == eid)
            .first()
        )
        row.next_attempt_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
        db.commit()

        with patch("app.services.notification_outbox.send_sms") as mock_sms, \
             patch("app.services.notification_outbox.get_settings") as mock_settings:
            s = MagicMock()
            s.enable_twilio = True
            s.database_url = "sqlite:///test"
            mock_settings.return_value = s

            sent = process_notification_outbox_once(db, batch_size=10, max_attempts=5)
            db.commit()

        assert sent == 0
        mock_sms.assert_not_called()

        row = (
            db.query(NotificationOutbox)
            .filter(NotificationOutbox.entity_id == eid)
            .first()
        )
        assert row.status == "PENDING"
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# Backoff tests
# ═══════════════════════════════════════════════════════════════


def test_compute_backoff_exponential():
    """Backoff should grow exponentially, capped at 3600 seconds."""
    from app.services.notification_outbox import _compute_backoff

    assert _compute_backoff(1) == timedelta(seconds=60)    # 2^0 * 60 = 60
    assert _compute_backoff(2) == timedelta(seconds=120)   # 2^1 * 60 = 120
    assert _compute_backoff(3) == timedelta(seconds=240)   # 2^2 * 60 = 240
    assert _compute_backoff(4) == timedelta(seconds=480)   # 2^3 * 60 = 480
    assert _compute_backoff(5) == timedelta(seconds=960)   # 2^4 * 60 = 960
    # Capped at 3600
    assert _compute_backoff(10) == timedelta(seconds=3600)


def test_compute_backoff_zero_attempt():
    """Attempt count 0 should produce minimum 60s backoff."""
    from app.services.notification_outbox import _compute_backoff

    assert _compute_backoff(0) == timedelta(seconds=60)


# ═══════════════════════════════════════════════════════════════
# Dedupe key tests
# ═══════════════════════════════════════════════════════════════


def test_dedupe_key_deterministic():
    """Same inputs should always produce the same dedupe key."""
    from app.services.notification_outbox import _dedupe_key

    key1 = _dedupe_key(
        channel="sms", template_key="T", entity_type="p",
        entity_id="123", payload_json={"a": 1},
    )
    key2 = _dedupe_key(
        channel="sms", template_key="T", entity_type="p",
        entity_id="123", payload_json={"a": 1},
    )
    assert key1 == key2


def test_dedupe_key_format():
    """Dedupe key should follow channel:template:entity_type:entity_id:hash format."""
    from app.services.notification_outbox import _dedupe_key

    key = _dedupe_key(
        channel="email", template_key="OFFER",
        entity_type="call_request", entity_id="abc-123",
        payload_json={"to": "x@y.com"},
    )
    parts = key.split(":")
    assert parts[0] == "email"
    assert parts[1] == "OFFER"
    assert parts[2] == "call_request"
    assert parts[3] == "abc-123"
    assert len(parts[4]) == 16  # hash digest truncated to 16 chars


# ═══════════════════════════════════════════════════════════════
# Channel helpers tests
# ═══════════════════════════════════════════════════════════════


def test_build_ics_invite():
    """ICS builder should produce valid calendar data."""
    from app.services.notification_outbox_channels import build_ics_invite

    ics = build_ics_invite(
        summary="Test Apziura",
        starts_at_utc=datetime(2026, 3, 1, 10, 0, 0),
        ends_at_utc=datetime(2026, 3, 1, 11, 0, 0),
        location="Vilnius",
    )
    text = ics.decode("utf-8")
    assert "BEGIN:VCALENDAR" in text
    assert "BEGIN:VEVENT" in text
    assert "SUMMARY:Test Apziura" in text
    assert "LOCATION:Vilnius" in text
    assert "DTSTART:20260301T100000Z" in text
    assert "DTEND:20260301T110000Z" in text
    assert "METHOD:REQUEST" in text


def test_build_offer_email_payload_with_ics():
    """Email payload builder should include base64-encoded ICS attachment."""
    import base64

    from app.services.notification_outbox_channels import build_offer_email_payload

    ics = b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"
    payload = build_offer_email_payload(
        to_email="test@example.com",
        subject="Pasiulymas",
        body_text="Sveiki",
        ics_bytes=ics,
    )
    assert payload["to"] == "test@example.com"
    assert payload["subject"] == "Pasiulymas"
    assert len(payload["attachments"]) == 1
    att = payload["attachments"][0]
    assert att["filename"] == "invite.ics"
    assert base64.b64decode(att["content_b64"]) == ics


def test_build_offer_email_payload_without_ics():
    """Email payload without ICS should have empty attachments."""
    from app.services.notification_outbox_channels import build_offer_email_payload

    payload = build_offer_email_payload(
        to_email="test@example.com",
        subject="Info",
        body_text="Sveiki",
        ics_bytes=None,
    )
    assert payload["attachments"] == []


def test_build_whatsapp_ping_payload():
    """WhatsApp payload builder should set to and message fields."""
    from app.services.notification_outbox_channels import build_whatsapp_ping_payload

    payload = build_whatsapp_ping_payload(
        phone="+37060000000", message="Labas",
    )
    assert payload["to"] == "+37060000000"
    assert payload["message"] == "Labas"


def test_outbox_channel_send_whatsapp_disabled():
    """WhatsApp send should be a no-op when disabled."""
    from app.services.notification_outbox_channels import outbox_channel_send

    # Should not raise, just return silently
    outbox_channel_send(
        channel="whatsapp_ping",
        payload={"to": "+37060000000", "message": "Test"},
        enable_whatsapp=False,
    )


def test_outbox_channel_send_whatsapp_enabled():
    """WhatsApp send should call Twilio client when enabled."""
    from app.services.notification_outbox_channels import outbox_channel_send

    with patch("app.services.notification_outbox_channels.send_whatsapp_via_twilio") as mock_send:
        outbox_channel_send(
            channel="whatsapp_ping",
            payload={"to": "+37060000000", "message": "Labas"},
            enable_whatsapp=True,
            twilio_account_sid="ACtest123",
            twilio_auth_token="token123",
            twilio_whatsapp_from_number="whatsapp:+14155238886",
        )
        mock_send.assert_called_once_with(
            {"to": "+37060000000", "message": "Labas"},
            account_sid="ACtest123",
            auth_token="token123",
            from_number="whatsapp:+14155238886",
        )


def test_whatsapp_via_twilio_sends_message():
    """send_whatsapp_via_twilio should create Twilio message with whatsapp: prefix."""
    from app.services.notification_outbox_channels import send_whatsapp_via_twilio

    with patch("app.services.notification_outbox_channels.Client") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client

        send_whatsapp_via_twilio(
            {"to": "+37060000000", "message": "Vizitas pakeistas"},
            account_sid="ACtest",
            auth_token="token",
            from_number="whatsapp:+14155238886",
        )

        MockClient.assert_called_once_with("ACtest", "token")
        mock_client.messages.create.assert_called_once_with(
            to="whatsapp:+37060000000",
            from_="whatsapp:+14155238886",
            body="Vizitas pakeistas",
        )


def test_whatsapp_no_from_number_raises():
    """send_whatsapp_via_twilio should raise when from_number is empty."""
    from app.services.notification_outbox_channels import send_whatsapp_via_twilio

    with pytest.raises(RuntimeError, match="WHATSAPP_FROM_NUMBER_NOT_CONFIGURED"):
        send_whatsapp_via_twilio(
            {"to": "+37060000000", "message": "Test"},
            account_sid="ACtest",
            auth_token="token",
            from_number="",
        )


def test_whatsapp_missing_fields_raises():
    """send_whatsapp_via_twilio should raise when payload has missing fields."""
    from app.services.notification_outbox_channels import send_whatsapp_via_twilio

    with pytest.raises(RuntimeError, match="WHATSAPP_MISSING_FIELDS"):
        send_whatsapp_via_twilio(
            {"to": "", "message": ""},
            account_sid="ACtest",
            auth_token="token",
            from_number="whatsapp:+14155238886",
        )


def test_whatsapp_adds_prefix_to_numbers():
    """send_whatsapp_via_twilio should add whatsapp: prefix if missing."""
    from app.services.notification_outbox_channels import send_whatsapp_via_twilio

    with patch("app.services.notification_outbox_channels.Client") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client

        # from_number without prefix — should be added
        send_whatsapp_via_twilio(
            {"to": "+37060000000", "message": "Test"},
            account_sid="ACtest",
            auth_token="token",
            from_number="+14155238886",
        )

        mock_client.messages.create.assert_called_once_with(
            to="whatsapp:+37060000000",
            from_="whatsapp:+14155238886",
            body="Test",
        )


def test_outbox_channel_send_sms_raises():
    """SMS via outbox_channel_send should raise — it uses legacy path."""
    from app.services.notification_outbox_channels import outbox_channel_send

    with pytest.raises(RuntimeError, match="SMS_USE_LEGACY_PATH"):
        outbox_channel_send(channel="sms", payload={})


def test_outbox_channel_send_unknown_raises():
    """Unknown channel should raise RuntimeError."""
    from app.services.notification_outbox_channels import outbox_channel_send

    with pytest.raises(RuntimeError, match="UNKNOWN_CHANNEL"):
        outbox_channel_send(channel="fax", payload={})


def test_outbox_channel_send_email_without_smtp_raises():
    """Email without SMTP config should raise."""
    from app.services.notification_outbox_channels import outbox_channel_send

    with pytest.raises(RuntimeError, match="SMTP_NOT_CONFIGURED"):
        outbox_channel_send(
            channel="email",
            payload={"to": "a@b.com", "subject": "X", "body_text": "Y"},
            smtp=None,
        )
