"""Tests for email auto-reply service and conversation tracking.

Covers:
- Missing-data reply enqueued when fields are missing
- Lithuanian template text correctness
- Rate limit (count >= max_per_cr) → None
- No-reply filter → None
- Auto-offer when questionnaire complete + both flags ON
- None when AUTO_OFFER=false
- Offer rate limit (max 1)
- Feature flag OFF → None
- Conversation tracking (reply merges into existing CR)
- Threading headers correctness
"""

import os
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.models.project import Base, CallRequest
from app.schemas.assistant import CallRequestStatus
from app.services.email_auto_reply import (
    _build_missing_data_body,
    _build_threading_headers,
    _is_no_reply,
    _redact_email_for_log,
    maybe_send_auto_reply,
)
from app.services.intake_service import _get_intake_state, _set_intake_state


def _make_cr(db, *, email="jonas@example.lt", name="Jonas", state=None):
    """Helper to create a CallRequest for testing."""
    cr = CallRequest(
        name=name,
        phone="",
        email=email,
        notes="Test notes",
        status=CallRequestStatus.NEW.value,
        source="email",
        intake_state=state or {},
    )
    db.add(cr)
    db.flush()
    return cr


def _set_questionnaire(cr, db, fields: dict):
    """Helper to set questionnaire fields on a CallRequest."""
    state = _get_intake_state(cr)
    q = state.setdefault("questionnaire", {})
    for key, value in fields.items():
        q[key] = {"value": value, "source": "email", "confidence": 1.0}
    _set_intake_state(cr, state)
    db.add(cr)
    db.flush()


class NoReplyFilterTests(unittest.TestCase):
    def test_noreply(self):
        self.assertTrue(_is_no_reply("noreply@example.lt"))

    def test_no_reply_with_hyphen(self):
        self.assertTrue(_is_no_reply("no-reply@example.lt"))

    def test_mailer_daemon(self):
        self.assertTrue(_is_no_reply("mailer-daemon@example.lt"))

    def test_postmaster(self):
        self.assertTrue(_is_no_reply("postmaster@example.lt"))

    def test_normal_email(self):
        self.assertFalse(_is_no_reply("jonas@example.lt"))

    def test_noreply_in_domain(self):
        # Only check local part.
        self.assertFalse(_is_no_reply("info@noreply.com"))

    def test_redact_email_for_log(self):
        self.assertEqual(_redact_email_for_log("jonas@example.lt"), "***as@example.lt")


class MissingDataBodyTests(unittest.TestCase):
    def test_body_contains_fields(self):
        body = _build_missing_data_body("Jonas", ["address", "phone"])
        self.assertIn("Jonas", body)
        self.assertIn("paslaugos vietos adresas", body)
        self.assertIn("telefono numeris", body)
        self.assertIn("VejaPRO komanda", body)

    def test_body_with_empty_name(self):
        body = _build_missing_data_body("", ["service_type"])
        self.assertIn("Kliente", body)
        self.assertIn("kokios paslaugos", body)


class ThreadingHeadersTests(unittest.TestCase):
    def setUp(self):
        get_settings.cache_clear()

    def tearDown(self):
        get_settings.cache_clear()

    @patch.dict(os.environ, {"CLOUDMAILIN_REPLY_TO_ADDRESS": "intake@test.cloudmailin.net"}, clear=False)
    def test_headers_with_message_id(self):
        state = {"inbound_email": {"message_id": "<abc123@example.lt>"}}
        headers = _build_threading_headers(state)
        self.assertEqual(headers["In-Reply-To"], "<abc123@example.lt>")
        self.assertEqual(headers["References"], "<abc123@example.lt>")
        self.assertEqual(headers["Reply-To"], "intake@test.cloudmailin.net")

    @patch.dict(os.environ, {"CLOUDMAILIN_REPLY_TO_ADDRESS": ""}, clear=False)
    def test_headers_without_reply_to(self):
        state = {"inbound_email": {"message_id": "<abc@test.lt>"}}
        headers = _build_threading_headers(state)
        self.assertIn("In-Reply-To", headers)
        self.assertNotIn("Reply-To", headers)

    def test_headers_without_inbound_email(self):
        state = {}
        headers = _build_threading_headers(state)
        self.assertNotIn("In-Reply-To", headers)


class MaybeSendAutoReplyTests(unittest.TestCase):
    def setUp(self):
        get_settings.cache_clear()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def tearDown(self):
        get_settings.cache_clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    @patch.dict(os.environ, {"ENABLE_EMAIL_AUTO_REPLY": "false"}, clear=False)
    def test_feature_flag_off_returns_none(self):
        db = self.SessionLocal()
        try:
            cr = _make_cr(db)
            result = maybe_send_auto_reply(db, call_request=cr)
            self.assertIsNone(result)
        finally:
            db.close()

    @patch.dict(os.environ, {"ENABLE_EMAIL_AUTO_REPLY": "true"}, clear=False)
    def test_no_reply_address_returns_none(self):
        db = self.SessionLocal()
        try:
            cr = _make_cr(db, email="noreply@example.lt")
            _set_questionnaire(cr, db, {"email": "noreply@example.lt"})
            result = maybe_send_auto_reply(db, call_request=cr)
            self.assertIsNone(result)
        finally:
            db.close()

    @patch.dict(os.environ, {"ENABLE_EMAIL_AUTO_REPLY": "true"}, clear=False)
    def test_no_email_returns_none(self):
        db = self.SessionLocal()
        try:
            cr = _make_cr(db, email="")
            result = maybe_send_auto_reply(db, call_request=cr)
            self.assertIsNone(result)
        finally:
            db.close()

    @patch.dict(os.environ, {"ENABLE_EMAIL_AUTO_REPLY": "true"}, clear=False)
    @patch("app.services.email_auto_reply.enqueue_notification")
    def test_missing_data_reply_enqueued(self, mock_enqueue):
        """When address and service_type are missing, enqueue auto-reply."""
        mock_enqueue.return_value = True
        db = self.SessionLocal()
        try:
            cr = _make_cr(db)
            _set_questionnaire(cr, db, {"email": "jonas@example.lt", "client_name": "Jonas"})

            result = maybe_send_auto_reply(db, call_request=cr)
            db.commit()

            self.assertEqual(result, "missing_data")
            mock_enqueue.assert_called_once()
            call_kwargs = mock_enqueue.call_args
            payload = call_kwargs.kwargs.get("payload_json") or call_kwargs[1].get("payload_json")
            self.assertEqual(payload["to"], "jonas@example.lt")
            self.assertIn("paslaugos vietos adresas", payload["body_text"])
            self.assertIn("kokios paslaugos", payload["body_text"])

            # Check state was updated.
            state = _get_intake_state(cr)
            ar = state.get("auto_replies", {})
            self.assertEqual(ar["missing_data"]["count"], 1)
            self.assertIn("last_sent_at", ar["missing_data"])
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {"ENABLE_EMAIL_AUTO_REPLY": "true", "EMAIL_AUTO_REPLY_MAX_PER_CR": "2"},
        clear=False,
    )
    @patch("app.services.email_auto_reply.enqueue_notification")
    def test_missing_data_rate_limit(self, mock_enqueue):
        """After max_per_cr replies, return None."""
        mock_enqueue.return_value = True
        db = self.SessionLocal()
        try:
            cr = _make_cr(db)
            _set_questionnaire(cr, db, {"email": "jonas@example.lt"})

            # Set auto_replies count to max.
            state = _get_intake_state(cr)
            state["auto_replies"] = {
                "missing_data": {
                    "count": 2,
                    "last_sent_at": "2026-01-01T00:00:00+00:00",
                }
            }
            _set_intake_state(cr, state)
            db.add(cr)
            db.flush()

            result = maybe_send_auto_reply(db, call_request=cr)
            self.assertIsNone(result)
            mock_enqueue.assert_not_called()
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {"ENABLE_EMAIL_AUTO_REPLY": "true", "ENABLE_EMAIL_AUTO_OFFER": "true", "ENABLE_SCHEDULE_ENGINE": "true"},
        clear=False,
    )
    @patch("app.services.email_auto_reply.send_offer_one_click")
    def test_offer_sent_when_complete(self, mock_offer):
        """When questionnaire is complete and flags are on, send offer."""
        db = self.SessionLocal()
        try:
            cr = _make_cr(db)
            _set_questionnaire(
                cr,
                db,
                {
                    "email": "jonas@example.lt",
                    "address": "Vilnius, Gedimino pr. 1",
                    "service_type": "vejos pjovimas",
                },
            )
            mock_offer.return_value = cr

            result = maybe_send_auto_reply(db, call_request=cr)
            db.commit()

            self.assertEqual(result, "offer_sent")
            mock_offer.assert_called_once()

            # Check state was updated.
            state = _get_intake_state(cr)
            ar = state.get("auto_replies", {})
            self.assertEqual(ar["offer"]["count"], 1)
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {"ENABLE_EMAIL_AUTO_REPLY": "true", "ENABLE_EMAIL_AUTO_OFFER": "false"},
        clear=False,
    )
    def test_no_offer_when_flag_off(self):
        """When AUTO_OFFER flag is off, don't send offer even if complete."""
        db = self.SessionLocal()
        try:
            cr = _make_cr(db)
            _set_questionnaire(
                cr,
                db,
                {
                    "email": "jonas@example.lt",
                    "address": "Vilnius",
                    "service_type": "vejos pjovimas",
                },
            )

            result = maybe_send_auto_reply(db, call_request=cr)
            self.assertIsNone(result)
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {"ENABLE_EMAIL_AUTO_REPLY": "true", "ENABLE_EMAIL_AUTO_OFFER": "true", "ENABLE_SCHEDULE_ENGINE": "true"},
        clear=False,
    )
    @patch("app.services.email_auto_reply.send_offer_one_click")
    def test_offer_rate_limit(self, mock_offer):
        """After 1 offer, don't send another."""
        db = self.SessionLocal()
        try:
            cr = _make_cr(db)
            _set_questionnaire(
                cr,
                db,
                {
                    "email": "jonas@example.lt",
                    "address": "Vilnius",
                    "service_type": "vejos pjovimas",
                },
            )

            # Mark offer already sent.
            state = _get_intake_state(cr)
            state["auto_replies"] = {"offer": {"count": 1, "last_sent_at": "2026-01-01T00:00:00+00:00"}}
            _set_intake_state(cr, state)
            db.add(cr)
            db.flush()

            result = maybe_send_auto_reply(db, call_request=cr)
            self.assertIsNone(result)
            mock_offer.assert_not_called()
        finally:
            db.close()

    @patch.dict(os.environ, {"ENABLE_EMAIL_AUTO_REPLY": "true"}, clear=False)
    @patch("app.services.email_auto_reply.enqueue_notification")
    def test_missing_data_min_interval(self, mock_enqueue):
        """Don't send again within MIN_REPLY_INTERVAL_S."""
        mock_enqueue.return_value = True
        db = self.SessionLocal()
        try:
            cr = _make_cr(db)
            _set_questionnaire(cr, db, {"email": "jonas@example.lt"})

            # Last sent just now (within interval).
            state = _get_intake_state(cr)
            state["auto_replies"] = {
                "missing_data": {
                    "count": 1,
                    "last_sent_at": datetime.now(timezone.utc).isoformat(),
                }
            }
            _set_intake_state(cr, state)
            db.add(cr)
            db.flush()

            result = maybe_send_auto_reply(db, call_request=cr)
            self.assertIsNone(result)
            mock_enqueue.assert_not_called()
        finally:
            db.close()


# ─── Conversation Tracking (Webhook Integration) ──────────


class ConversationTrackingTests(unittest.TestCase):
    """Test that reply emails merge into existing CR via webhook."""

    def setUp(self):
        from app.core.dependencies import get_db
        from app.main import app as fastapi_app
        from app.utils.rate_limit import rate_limiter

        get_settings.cache_clear()
        rate_limiter.reset()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        self.app = fastapi_app
        self.app.dependency_overrides[get_db] = override_get_db

        from fastapi.testclient import TestClient

        self.client = TestClient(self.app)

    def tearDown(self):
        get_settings.cache_clear()
        self.client.close()
        self.app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    @patch.dict(
        os.environ,
        {
            "ENABLE_EMAIL_WEBHOOK": "true",
            "CLOUDMAILIN_USERNAME": "",
            "CLOUDMAILIN_PASSWORD": "",
            "ENABLE_EMAIL_AUTO_REPLY": "true",
        },
        clear=False,
    )
    @patch("app.services.email_auto_reply.enqueue_notification")
    def test_reply_merges_into_existing_cr(self, mock_enqueue):
        """Second email from same sender merges into existing CR."""
        mock_enqueue.return_value = True

        # First email — creates CR.
        payload1 = {
            "envelope": {"from": "jonas@example.lt", "to": "intake@vejapro.lt"},
            "headers": {
                "from": "Jonas <jonas@example.lt>",
                "subject": "Reikia vejos pjovimo",
                "message_id": f"<{uuid.uuid4().hex}@example.lt>",
            },
            "plain": "Noriu vejos pjovimo",
            "reply_plain": "",
        }
        resp1 = self.client.post("/api/v1/webhook/email/inbound", json=payload1)
        self.assertEqual(resp1.status_code, 200)
        cr_id = resp1.json()["call_request_id"]

        # Second email — reply from same sender, different Message-Id.
        payload2 = {
            "envelope": {"from": "jonas@example.lt", "to": "intake@vejapro.lt"},
            "headers": {
                "from": "Jonas <jonas@example.lt>",
                "subject": "Re: Reikia vejos pjovimo",
                "message_id": f"<{uuid.uuid4().hex}@example.lt>",
            },
            "plain": "Adresas: Vilnius, Gedimino pr. 15. Plotas 500 kv.m.",
            "reply_plain": "Adresas: Vilnius, Gedimino pr. 15. Plotas 500 kv.m.",
        }
        resp2 = self.client.post("/api/v1/webhook/email/inbound", json=payload2)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json()["status"], "reply_merged")
        self.assertEqual(resp2.json()["call_request_id"], cr_id)

        # Verify notes were appended.
        db = self.SessionLocal()
        try:
            cr = db.get(CallRequest, cr_id)
            self.assertIn("Noriu vejos pjovimo", cr.notes)
            self.assertIn("Reply", cr.notes)
            self.assertIn("Gedimino pr. 15", cr.notes)
        finally:
            db.close()
