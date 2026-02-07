import pytest


def test_notification_outbox_dedupe_key_idempotent():
    from app.core.dependencies import SessionLocal

    if SessionLocal is None:
        pytest.skip("DATABASE_URL is not configured")

    from app.models.project import NotificationOutbox
    from app.services.notification_outbox import enqueue_notification

    db = SessionLocal()
    try:
        created1 = enqueue_notification(
            db,
            entity_type="test",
            entity_id="00000000-0000-0000-0000-000000000111",
            channel="sms",
            template_key="TEST",
            payload_json={"to_number": "+37060000000", "body": "Test"},
        )
        created2 = enqueue_notification(
            db,
            entity_type="test",
            entity_id="00000000-0000-0000-0000-000000000111",
            channel="sms",
            template_key="TEST",
            payload_json={"to_number": "+37060000000", "body": "Test"},
        )
        db.commit()

        assert created1 is True
        assert created2 is False

        count = (
            db.query(NotificationOutbox)
            .filter(NotificationOutbox.entity_type == "test")
            .filter(NotificationOutbox.entity_id == "00000000-0000-0000-0000-000000000111")
            .count()
        )
        assert count == 1
    finally:
        db.close()
