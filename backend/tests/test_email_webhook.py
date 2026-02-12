"""Tests for CloudMailin inbound email webhook.

Covers:
- Basic Auth verification
- Feature flag gating
- Rate limiting
- Idempotency (Message-Id dedup)
- CallRequest creation with email header data
- AI conversation extract integration
- merge_ai_suggestions with email-sourced fields
"""

import base64
import json
import os
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_db
from app.main import app
from app.models.project import Base, CallRequest
from app.utils.rate_limit import rate_limiter

TEST_USERNAME = "vejapro-test"
TEST_PASSWORD = "test-secret-password-123"


def _basic_auth_header(username: str = TEST_USERNAME, password: str = TEST_PASSWORD) -> dict:
    """Build HTTP Basic Auth header."""
    creds = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {creds}"}


def _build_cloudmailin_payload(
    *,
    sender: str = "jonas@example.lt",
    from_header: str = "Jonas Petraitis <jonas@example.lt>",
    subject: str = "Reikia vejos pjovimo",
    plain: str = "Labas, noriu vejos pjovimo Gedimino pr. 15, Vilnius.",
    reply_plain: str = "",
    message_id: str = "",
    recipient: str = "intake@vejapro.lt",
):
    """Build CloudMailin JSON Normalized payload."""
    if not message_id:
        message_id = f"<{uuid.uuid4().hex}@example.lt>"

    return {
        "envelope": {
            "to": recipient,
            "from": sender,
            "recipients": [recipient],
            "remote_ip": "127.0.0.1",
            "spf": {"result": "pass", "domain": "example.lt"},
            "tls": True,
        },
        "headers": {
            "from": from_header,
            "to": recipient,
            "subject": subject,
            "message_id": message_id,
        },
        "plain": plain,
        "html": "",
        "reply_plain": reply_plain,
        "attachments": [],
    }


# ─── Basic Auth Tests ──────────────────────


class BasicAuthTests(unittest.TestCase):
    """Tests for verify_basic_auth()."""

    def test_valid_credentials(self):
        from unittest.mock import MagicMock

        from app.api.v1.email_webhook import verify_basic_auth

        creds = base64.b64encode(b"user:pass").decode("ascii")
        req = MagicMock()
        req.headers = {"Authorization": f"Basic {creds}"}
        self.assertTrue(verify_basic_auth(req, "user", "pass"))

    def test_wrong_password(self):
        from unittest.mock import MagicMock

        from app.api.v1.email_webhook import verify_basic_auth

        creds = base64.b64encode(b"user:wrong").decode("ascii")
        req = MagicMock()
        req.headers = {"Authorization": f"Basic {creds}"}
        self.assertFalse(verify_basic_auth(req, "user", "pass"))

    def test_no_auth_header(self):
        from unittest.mock import MagicMock

        from app.api.v1.email_webhook import verify_basic_auth

        req = MagicMock()
        req.headers = {}
        self.assertFalse(verify_basic_auth(req, "user", "pass"))

    def test_bearer_instead_of_basic(self):
        from unittest.mock import MagicMock

        from app.api.v1.email_webhook import verify_basic_auth

        req = MagicMock()
        req.headers = {"Authorization": "Bearer some-token"}
        self.assertFalse(verify_basic_auth(req, "user", "pass"))

    def test_invalid_base64(self):
        from unittest.mock import MagicMock

        from app.api.v1.email_webhook import verify_basic_auth

        req = MagicMock()
        req.headers = {"Authorization": "Basic not-valid-base64!!!"}
        self.assertFalse(verify_basic_auth(req, "user", "pass"))


# ─── From Header Parsing Tests ──────────────────────


class FromHeaderParsingTests(unittest.TestCase):
    """Tests for _parse_from_name()."""

    def test_name_and_email(self):
        from app.api.v1.email_webhook import _parse_from_name

        self.assertEqual(_parse_from_name("Jonas Petraitis <jonas@example.lt>"), "Jonas Petraitis")

    def test_quoted_name(self):
        from app.api.v1.email_webhook import _parse_from_name

        self.assertEqual(_parse_from_name('"Jonas Petraitis" <jonas@example.lt>'), "Jonas Petraitis")

    def test_email_only(self):
        from app.api.v1.email_webhook import _parse_from_name

        self.assertEqual(_parse_from_name("jonas@example.lt"), "")

    def test_empty(self):
        from app.api.v1.email_webhook import _parse_from_name

        self.assertEqual(_parse_from_name(""), "")


# ─── Endpoint Tests ──────────────────────────────────


class EmailWebhookEndpointTests(unittest.TestCase):
    """Tests for POST /api/v1/webhook/email/inbound."""

    def setUp(self):
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

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    @patch.dict(
        os.environ,
        {"ENABLE_EMAIL_WEBHOOK": "false"},
        clear=False,
    )
    def test_disabled_returns_404(self):
        resp = self.client.post("/api/v1/webhook/email/inbound", json={"envelope": {}})
        self.assertEqual(resp.status_code, 404)

    @patch.dict(
        os.environ,
        {
            "ENABLE_EMAIL_WEBHOOK": "true",
            "CLOUDMAILIN_USERNAME": TEST_USERNAME,
            "CLOUDMAILIN_PASSWORD": TEST_PASSWORD,
        },
        clear=False,
    )
    def test_invalid_auth_returns_403(self):
        payload = _build_cloudmailin_payload()
        bad_header = _basic_auth_header("wrong-user", "wrong-pass")
        resp = self.client.post("/api/v1/webhook/email/inbound", json=payload, headers=bad_header)
        self.assertEqual(resp.status_code, 403)

    @patch.dict(
        os.environ,
        {
            "ENABLE_EMAIL_WEBHOOK": "true",
            "CLOUDMAILIN_USERNAME": TEST_USERNAME,
            "CLOUDMAILIN_PASSWORD": TEST_PASSWORD,
        },
        clear=False,
    )
    def test_no_auth_header_returns_403(self):
        payload = _build_cloudmailin_payload()
        resp = self.client.post("/api/v1/webhook/email/inbound", json=payload)
        self.assertEqual(resp.status_code, 403)

    @patch.dict(
        os.environ,
        {
            "ENABLE_EMAIL_WEBHOOK": "true",
            "CLOUDMAILIN_USERNAME": "",
            "CLOUDMAILIN_PASSWORD": "",
        },
        clear=False,
    )
    def test_no_credentials_configured_allows_all(self):
        """When CLOUDMAILIN_USERNAME/PASSWORD are empty, skip auth (dev mode)."""
        payload = _build_cloudmailin_payload()
        resp = self.client.post("/api/v1/webhook/email/inbound", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    @patch.dict(
        os.environ,
        {
            "ENABLE_EMAIL_WEBHOOK": "true",
            "CLOUDMAILIN_USERNAME": TEST_USERNAME,
            "CLOUDMAILIN_PASSWORD": TEST_PASSWORD,
        },
        clear=False,
    )
    def test_valid_auth_accepted(self):
        payload = _build_cloudmailin_payload()
        headers = _basic_auth_header()
        resp = self.client.post("/api/v1/webhook/email/inbound", json=payload, headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    @patch.dict(
        os.environ,
        {
            "ENABLE_EMAIL_WEBHOOK": "true",
            "CLOUDMAILIN_USERNAME": "",
            "CLOUDMAILIN_PASSWORD": "",
        },
        clear=False,
    )
    def test_creates_call_request(self):
        payload = _build_cloudmailin_payload(
            sender="petras@example.lt",
            from_header="Petras Jonaitis <petras@example.lt>",
            subject="Vejos aeracija",
            plain="Noriu aeracijos, plotas 200 kv.m., Kaunas, Laisves al. 10",
        )
        resp = self.client.post("/api/v1/webhook/email/inbound", json=payload)
        self.assertEqual(resp.status_code, 200)

        cr_id = resp.json()["call_request_id"]
        db = self.SessionLocal()
        try:
            cr = db.get(CallRequest, cr_id)
            self.assertIsNotNone(cr)
            self.assertEqual(cr.source, "email")
            self.assertEqual(cr.email, "petras@example.lt")
            self.assertEqual(cr.name, "Petras Jonaitis")
            self.assertIn("Vejos aeracija", cr.notes)
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {
            "ENABLE_EMAIL_WEBHOOK": "true",
            "CLOUDMAILIN_USERNAME": "",
            "CLOUDMAILIN_PASSWORD": "",
        },
        clear=False,
    )
    def test_populates_intake_state_from_headers(self):
        payload = _build_cloudmailin_payload(
            sender="ona@example.lt",
            from_header="Ona Kazlauskiene <ona@example.lt>",
        )
        resp = self.client.post("/api/v1/webhook/email/inbound", json=payload)
        self.assertEqual(resp.status_code, 200)

        cr_id = resp.json()["call_request_id"]
        db = self.SessionLocal()
        try:
            cr = db.get(CallRequest, cr_id)
            state = cr.intake_state or {}
            q = state.get("questionnaire", {})

            # Email should be populated with confidence 1.0.
            self.assertEqual(q["email"]["value"], "ona@example.lt")
            self.assertEqual(q["email"]["confidence"], 1.0)
            self.assertEqual(q["email"]["source"], "email")

            # Name should be populated with confidence 0.9.
            self.assertEqual(q["client_name"]["value"], "Ona Kazlauskiene")
            self.assertEqual(q["client_name"]["confidence"], 0.9)
            self.assertEqual(q["client_name"]["source"], "email")

            # Inbound email metadata should be stored.
            inbound = state.get("inbound_email", {})
            self.assertIn("message_id", inbound)
            self.assertIn("received_at", inbound)
            self.assertEqual(inbound["subject"], "Reikia vejos pjovimo")
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {
            "ENABLE_EMAIL_WEBHOOK": "true",
            "CLOUDMAILIN_USERNAME": "",
            "CLOUDMAILIN_PASSWORD": "",
        },
        clear=False,
    )
    def test_idempotent_by_message_id(self):
        message_id = f"<{uuid.uuid4().hex}@example.lt>"
        payload = _build_cloudmailin_payload(message_id=message_id)

        resp1 = self.client.post("/api/v1/webhook/email/inbound", json=payload)
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp1.json()["status"], "ok")
        cr_id1 = resp1.json()["call_request_id"]

        # Second request with same Message-Id should return duplicate.
        resp2 = self.client.post("/api/v1/webhook/email/inbound", json=payload)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json()["status"], "duplicate")
        self.assertEqual(resp2.json()["call_request_id"], cr_id1)

        # Only one CallRequest should exist.
        db = self.SessionLocal()
        try:
            count = db.execute(select(CallRequest).where(CallRequest.source == "email")).scalars().all()
            self.assertEqual(len(count), 1)
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {
            "ENABLE_EMAIL_WEBHOOK": "true",
            "CLOUDMAILIN_USERNAME": "",
            "CLOUDMAILIN_PASSWORD": "",
        },
        clear=False,
    )
    def test_empty_body_creates_cr(self):
        payload = _build_cloudmailin_payload(plain="", reply_plain="")
        resp = self.client.post("/api/v1/webhook/email/inbound", json=payload)
        self.assertEqual(resp.status_code, 200)

        cr_id = resp.json()["call_request_id"]
        db = self.SessionLocal()
        try:
            cr = db.get(CallRequest, cr_id)
            self.assertIsNotNone(cr)
            self.assertEqual(cr.source, "email")
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {
            "ENABLE_EMAIL_WEBHOOK": "true",
            "CLOUDMAILIN_USERNAME": "",
            "CLOUDMAILIN_PASSWORD": "",
        },
        clear=False,
    )
    def test_no_name_uses_email(self):
        """When From header has no display name, use email as name."""
        payload = _build_cloudmailin_payload(
            sender="info@klientas.lt",
            from_header="info@klientas.lt",
        )
        resp = self.client.post("/api/v1/webhook/email/inbound", json=payload)
        self.assertEqual(resp.status_code, 200)

        cr_id = resp.json()["call_request_id"]
        db = self.SessionLocal()
        try:
            cr = db.get(CallRequest, cr_id)
            self.assertEqual(cr.name, "info@klientas.lt")
            state = cr.intake_state or {}
            q = state.get("questionnaire", {})
            # No client_name when from header has no display name.
            self.assertNotIn("client_name", q)
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {
            "ENABLE_EMAIL_WEBHOOK": "true",
            "CLOUDMAILIN_USERNAME": "",
            "CLOUDMAILIN_PASSWORD": "",
        },
        clear=False,
    )
    def test_reply_plain_preferred_over_plain(self):
        """reply_plain (stripped reply) should be used over full plain text."""
        payload = _build_cloudmailin_payload(
            plain="Original long email with signatures and quoted text...",
            reply_plain="Tik atsakymas: noriu vejos pjovimo",
        )
        resp = self.client.post("/api/v1/webhook/email/inbound", json=payload)
        self.assertEqual(resp.status_code, 200)

        cr_id = resp.json()["call_request_id"]
        db = self.SessionLocal()
        try:
            cr = db.get(CallRequest, cr_id)
            self.assertIn("Tik atsakymas", cr.notes)
            self.assertNotIn("Original long email", cr.notes)
        finally:
            db.close()


# ─── AI Integration Tests ──────────────────────


class EmailWebhookAITests(unittest.TestCase):
    """Tests for AI extraction integration in email webhook."""

    def setUp(self):
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

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    @patch.dict(
        os.environ,
        {
            "ENABLE_EMAIL_WEBHOOK": "true",
            "CLOUDMAILIN_USERNAME": "",
            "CLOUDMAILIN_PASSWORD": "",
            "ENABLE_AI_CONVERSATION_EXTRACT": "true",
            "AI_CONVERSATION_EXTRACT_PROVIDER": "mock",
            "AI_ALLOWED_PROVIDERS": "mock",
        },
        clear=False,
    )
    def test_ai_extraction_runs_on_body(self):
        """When AI flag is on, extraction runs and merges results."""
        from app.services.ai.common.providers.base import ProviderResult

        mock_json = json.dumps(
            {
                "client_name": {"value": "Jonas Petraitis", "confidence": 0.95},
                "phone": {"value": "+37065512345", "confidence": 0.9},
                "email": {"value": "jonas@example.lt", "confidence": 0.8},
                "address": {"value": "Gedimino pr. 15, Vilnius", "confidence": 0.85},
                "service_type": {"value": "vejos pjovimas", "confidence": 0.8},
                "urgency": {"value": "", "confidence": 0.0},
                "area_m2": {"value": "300", "confidence": 0.7},
            }
        )

        mock_provider = AsyncMock()
        mock_provider.name = "mock"
        mock_provider.generate.return_value = ProviderResult(raw_text=mock_json, model="test", provider="mock")

        payload = _build_cloudmailin_payload(
            sender="jonas@example.lt",
            from_header="Jonas Petraitis <jonas@example.lt>",
            plain="Labas, noriu vejos pjovimo Gedimino pr. 15, Vilnius. Plotas 300 kv.m. Tel 865512345",
        )

        with patch("app.services.ai.common.router.get_provider", return_value=mock_provider):
            resp = self.client.post("/api/v1/webhook/email/inbound", json=payload)

        self.assertEqual(resp.status_code, 200)

        cr_id = resp.json()["call_request_id"]
        db = self.SessionLocal()
        try:
            cr = db.get(CallRequest, cr_id)
            state = cr.intake_state or {}
            q = state.get("questionnaire", {})

            # Email header data should remain (confidence=1.0 > AI confidence=0.8).
            self.assertEqual(q["email"]["value"], "jonas@example.lt")
            self.assertEqual(q["email"]["source"], "email")
            self.assertEqual(q["email"]["confidence"], 1.0)

            # AI should have added address.
            self.assertIn("address", q)
            self.assertEqual(q["address"]["value"], "Gedimino pr. 15, Vilnius")
            self.assertEqual(q["address"]["source"], "ai")

            # AI should have added service_type.
            self.assertIn("service_type", q)
            self.assertEqual(q["service_type"]["value"], "vejos pjovimas")

            # AI should have added area_m2.
            self.assertIn("area_m2", q)
            self.assertEqual(q["area_m2"]["value"], "300")
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {
            "ENABLE_EMAIL_WEBHOOK": "true",
            "CLOUDMAILIN_USERNAME": "",
            "CLOUDMAILIN_PASSWORD": "",
            "ENABLE_AI_CONVERSATION_EXTRACT": "false",
        },
        clear=False,
    )
    def test_no_ai_when_flag_off(self):
        """When AI flag is off, CallRequest created but no AI fields."""
        payload = _build_cloudmailin_payload(
            plain="Noriu vejos pjovimo, adresas Vilnius Gedimino 15",
        )
        resp = self.client.post("/api/v1/webhook/email/inbound", json=payload)
        self.assertEqual(resp.status_code, 200)

        cr_id = resp.json()["call_request_id"]
        db = self.SessionLocal()
        try:
            cr = db.get(CallRequest, cr_id)
            state = cr.intake_state or {}
            q = state.get("questionnaire", {})

            # Email header data should still be there.
            self.assertIn("email", q)

            # But no AI-sourced fields (address, service_type) since AI is off.
            if "address" in q:
                self.assertNotEqual(q["address"].get("source"), "ai")
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {
            "ENABLE_EMAIL_WEBHOOK": "true",
            "CLOUDMAILIN_USERNAME": "",
            "CLOUDMAILIN_PASSWORD": "",
            "ENABLE_AI_CONVERSATION_EXTRACT": "true",
            "AI_CONVERSATION_EXTRACT_PROVIDER": "mock",
            "AI_ALLOWED_PROVIDERS": "mock",
        },
        clear=False,
    )
    def test_email_header_not_overwritten_by_ai(self):
        """Email from header (confidence=1.0) should NOT be overwritten by AI (lower confidence)."""
        from app.services.ai.common.providers.base import ProviderResult

        # AI returns a different email with confidence=0.8.
        mock_json = json.dumps(
            {
                "client_name": {"value": "Kitas Vardas", "confidence": 0.6},
                "phone": {"value": "", "confidence": 0.0},
                "email": {"value": "kitas@example.lt", "confidence": 0.8},
                "address": {"value": "Kauno g. 5", "confidence": 0.7},
                "service_type": {"value": "", "confidence": 0.0},
                "urgency": {"value": "", "confidence": 0.0},
                "area_m2": {"value": "", "confidence": 0.0},
            }
        )

        mock_provider = AsyncMock()
        mock_provider.name = "mock"
        mock_provider.generate.return_value = ProviderResult(raw_text=mock_json, model="test", provider="mock")

        payload = _build_cloudmailin_payload(
            sender="realus@example.lt",
            from_header="Realus Vardas <realus@example.lt>",
        )

        with patch("app.services.ai.common.router.get_provider", return_value=mock_provider):
            resp = self.client.post("/api/v1/webhook/email/inbound", json=payload, headers=_basic_auth_header())

        self.assertEqual(resp.status_code, 200)

        cr_id = resp.json()["call_request_id"]
        db = self.SessionLocal()
        try:
            cr = db.get(CallRequest, cr_id)
            state = cr.intake_state or {}
            q = state.get("questionnaire", {})

            # Email from header should NOT be overwritten (1.0 > 0.8).
            self.assertEqual(q["email"]["value"], "realus@example.lt")
            self.assertEqual(q["email"]["source"], "email")
            self.assertEqual(q["email"]["confidence"], 1.0)

            # client_name from header (0.9) should NOT be overwritten by AI (0.6).
            self.assertEqual(q["client_name"]["value"], "Realus Vardas")
            self.assertEqual(q["client_name"]["source"], "email")

            # But AI should still add new fields like address.
            self.assertIn("address", q)
            self.assertEqual(q["address"]["value"], "Kauno g. 5")
            self.assertEqual(q["address"]["source"], "ai")
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {
            "ENABLE_EMAIL_WEBHOOK": "true",
            "CLOUDMAILIN_USERNAME": "",
            "CLOUDMAILIN_PASSWORD": "",
            "ENABLE_AI_CONVERSATION_EXTRACT": "true",
            "AI_CONVERSATION_EXTRACT_PROVIDER": "mock",
            "AI_ALLOWED_PROVIDERS": "mock",
        },
        clear=False,
    )
    def test_ai_failure_doesnt_break_webhook(self):
        """If AI extraction fails, CallRequest should still be created."""
        mock_provider = AsyncMock()
        mock_provider.name = "mock"
        mock_provider.generate.side_effect = RuntimeError("AI service down")

        payload = _build_cloudmailin_payload(plain="Noriu paslaugos")

        with patch("app.services.ai.common.router.get_provider", return_value=mock_provider):
            resp = self.client.post("/api/v1/webhook/email/inbound", json=payload)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

        cr_id = resp.json()["call_request_id"]
        db = self.SessionLocal()
        try:
            cr = db.get(CallRequest, cr_id)
            self.assertIsNotNone(cr)
            self.assertEqual(cr.source, "email")
        finally:
            db.close()
