import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from unittest.mock import patch

from httpx import Client, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from twilio.request_validator import RequestValidator

# Ensure backend/app is importable
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.main import app
from app.core.dependencies import get_db
from app.core.config import get_settings
from app.models.project import Base, Project, Payment, SmsConfirmation
from app.utils.rate_limit import rate_limiter


class WebhookIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["STRIPE_SECRET_KEY"] = "sk_test_dummy"
        os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_dummy"
        os.environ["TWILIO_AUTH_TOKEN"] = "twilio_dummy"
        os.environ["TWILIO_FROM_NUMBER"] = "+10000000000"
        os.environ["SUPABASE_JWT_SECRET"] = "jwt_dummy"
        get_settings.cache_clear()

    def setUp(self):
        rate_limiter.reset()
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        transport = ASGITransport(app=app)
        self.client = Client(transport=transport, base_url="http://testserver")

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _create_project(self, status: str, is_certified: bool = False):
        db = self.SessionLocal()
        project = Project(
            client_info={"phone": "+10000000001", "client_id": "client-1"},
            status=status,
            is_certified=is_certified,
            marketing_consent=True,
            marketing_consent_at=datetime.now(timezone.utc),
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        db.close()
        return project

    def test_stripe_deposit_moves_to_paid(self):
        project = self._create_project("DRAFT", is_certified=False)

        event = {
            "id": "evt_deposit_1",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_deposit",
                    "amount_received": 5000,
                    "currency": "eur",
                    "metadata": {"project_id": str(project.id), "payment_type": "deposit"},
                }
            },
        }

        with patch("stripe.Webhook.construct_event", return_value=event):
            resp = self.client.post("/api/v1/webhook/stripe", data="{}", headers={"stripe-signature": "sig"})

        self.assertEqual(resp.status_code, 200)

        db = self.SessionLocal()
        refreshed = db.get(Project, project.id)
        self.assertEqual(refreshed.status, "PAID")
        db.close()

    def test_stripe_final_creates_sms_confirmation(self):
        project = self._create_project("CERTIFIED", is_certified=True)

        event = {
            "id": "evt_final_1",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_final",
                    "amount_received": 10000,
                    "currency": "eur",
                    "metadata": {"project_id": str(project.id), "payment_type": "final"},
                }
            },
        }

        with patch("stripe.Webhook.construct_event", return_value=event):
            with patch("app.api.v1.projects.send_sms", return_value=None):
                resp = self.client.post("/api/v1/webhook/stripe", data="{}", headers={"stripe-signature": "sig"})

        self.assertEqual(resp.status_code, 200)

        db = self.SessionLocal()
        count = db.query(SmsConfirmation).filter(SmsConfirmation.project_id == project.id).count()
        self.assertEqual(count, 1)
        db.close()

    def test_twilio_invalid_signature(self):
        resp = self.client.post(
            "/api/v1/webhook/twilio",
            data={"Body": "TAIP ABCD", "From": "+10000000002"},
            headers={"X-Twilio-Signature": "bad"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_twilio_expired_token(self):
        project = self._create_project("CERTIFIED", is_certified=True)
        token = "EXPIRED1"
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        db = self.SessionLocal()
        confirmation = SmsConfirmation(
            project_id=project.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            status="PENDING",
            attempts=0,
        )
        db.add(confirmation)
        db.commit()
        db.close()

        validator = RequestValidator(os.environ["TWILIO_AUTH_TOKEN"])
        url = "http://testserver/api/v1/webhook/twilio"
        params = {"Body": f"TAIP {token}", "From": "+10000000003"}
        signature = validator.compute_signature(url, params)

        resp = self.client.post("/api/v1/webhook/twilio", data=params, headers={"X-Twilio-Signature": signature})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["ok"], False)

        db = self.SessionLocal()
        refreshed = db.get(SmsConfirmation, confirmation.id)
        self.assertEqual(refreshed.status, "EXPIRED")
        db.close()

    def test_twilio_attempts_limit(self):
        project = self._create_project("CERTIFIED", is_certified=True)
        token = "LIMIT1"
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        db = self.SessionLocal()
        confirmation = SmsConfirmation(
            project_id=project.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            status="PENDING",
            attempts=3,
        )
        db.add(confirmation)
        db.commit()
        db.close()

        validator = RequestValidator(os.environ["TWILIO_AUTH_TOKEN"])
        url = "http://testserver/api/v1/webhook/twilio"
        params = {"Body": f"TAIP {token}", "From": "+10000000004"}
        signature = validator.compute_signature(url, params)

        resp = self.client.post("/api/v1/webhook/twilio", data=params, headers={"X-Twilio-Signature": signature})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["ok"], False)

        db = self.SessionLocal()
        refreshed = db.get(SmsConfirmation, confirmation.id)
        self.assertEqual(refreshed.status, "FAILED")
        db.close()

    def test_twilio_valid_signature_activates_project(self):
        project = self._create_project("CERTIFIED", is_certified=True)

        db = self.SessionLocal()
        payment = Payment(
            project_id=project.id,
            provider="stripe",
            provider_intent_id="pi_final",
            provider_event_id="evt_final_ok",
            amount=100.0,
            currency="EUR",
            payment_type="FINAL",
            status="SUCCEEDED",
        )
        db.add(payment)
        db.commit()

        token = "VALID1"
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        confirmation = SmsConfirmation(
            project_id=project.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            status="PENDING",
            attempts=0,
        )
        db.add(confirmation)
        db.commit()
        db.close()

        validator = RequestValidator(os.environ["TWILIO_AUTH_TOKEN"])
        url = "http://testserver/api/v1/webhook/twilio"
        params = {"Body": f"TAIP {token}", "From": "+10000000005"}
        signature = validator.compute_signature(url, params)

        resp = self.client.post("/api/v1/webhook/twilio", data=params, headers={"X-Twilio-Signature": signature})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["ok"], True)

        db = self.SessionLocal()
        refreshed_project = db.get(Project, project.id)
        refreshed_confirmation = db.get(SmsConfirmation, confirmation.id)
        self.assertEqual(refreshed_project.status, "ACTIVE")
        self.assertEqual(refreshed_confirmation.status, "CONFIRMED")
        db.close()

    def test_twilio_rate_limit_by_ip(self):
        settings = get_settings()
        orig_ip_limit = settings.rate_limit_twilio_ip_per_min
        orig_from_limit = settings.rate_limit_twilio_from_per_min
        settings.rate_limit_twilio_ip_per_min = 1
        settings.rate_limit_twilio_from_per_min = 100

        try:
            validator = RequestValidator(os.environ["TWILIO_AUTH_TOKEN"])
            url = "http://testserver/api/v1/webhook/twilio"
            params = {"Body": "TAIP ABCD", "From": "+10000000006"}
            signature = validator.compute_signature(url, params)
            headers = {"X-Twilio-Signature": signature, "x-forwarded-for": "1.1.1.1"}

            resp1 = self.client.post("/api/v1/webhook/twilio", data=params, headers=headers)
            resp2 = self.client.post("/api/v1/webhook/twilio", data=params, headers=headers)

            self.assertEqual(resp1.status_code, 200)
            self.assertEqual(resp2.status_code, 429)
        finally:
            settings.rate_limit_twilio_ip_per_min = orig_ip_limit
            settings.rate_limit_twilio_from_per_min = orig_from_limit

    def test_twilio_rate_limit_by_from(self):
        settings = get_settings()
        orig_ip_limit = settings.rate_limit_twilio_ip_per_min
        orig_from_limit = settings.rate_limit_twilio_from_per_min
        settings.rate_limit_twilio_ip_per_min = 100
        settings.rate_limit_twilio_from_per_min = 1

        try:
            validator = RequestValidator(os.environ["TWILIO_AUTH_TOKEN"])
            url = "http://testserver/api/v1/webhook/twilio"
            params = {"Body": "TAIP ABCD", "From": "+10000000007"}
            signature = validator.compute_signature(url, params)
            headers = {"X-Twilio-Signature": signature, "x-forwarded-for": "2.2.2.2"}

            resp1 = self.client.post("/api/v1/webhook/twilio", data=params, headers=headers)
            resp2 = self.client.post("/api/v1/webhook/twilio", data=params, headers=headers)

            self.assertEqual(resp1.status_code, 200)
            self.assertEqual(resp2.status_code, 429)
        finally:
            settings.rate_limit_twilio_ip_per_min = orig_ip_limit
            settings.rate_limit_twilio_from_per_min = orig_from_limit

    def test_stripe_rate_limit_by_ip_and_idempotency(self):
        settings = get_settings()
        orig_limit = settings.rate_limit_stripe_ip_per_min
        settings.rate_limit_stripe_ip_per_min = 2

        try:
            project = self._create_project("DRAFT", is_certified=False)
            event = {
                "id": "evt_deposit_rl_1",
                "type": "payment_intent.succeeded",
                "data": {
                    "object": {
                        "id": "pi_deposit_rl",
                        "amount_received": 5000,
                        "currency": "eur",
                        "metadata": {"project_id": str(project.id), "payment_type": "deposit"},
                    }
                },
            }
            headers = {"stripe-signature": "sig", "x-forwarded-for": "3.3.3.3"}

            with patch("stripe.Webhook.construct_event", return_value=event):
                resp1 = self.client.post("/api/v1/webhook/stripe", data="{}", headers=headers)
                resp2 = self.client.post("/api/v1/webhook/stripe", data="{}", headers=headers)
                resp3 = self.client.post("/api/v1/webhook/stripe", data="{}", headers=headers)

            self.assertEqual(resp1.status_code, 200)
            self.assertEqual(resp2.status_code, 200)
            self.assertEqual(resp3.status_code, 429)

            db = self.SessionLocal()
            payment_count = db.query(Payment).filter(Payment.project_id == project.id).count()
            refreshed = db.get(Project, project.id)
            self.assertEqual(payment_count, 1)
            self.assertEqual(refreshed.status, "PAID")
            db.close()
        finally:
            settings.rate_limit_stripe_ip_per_min = orig_limit


if __name__ == "__main__":
    unittest.main()
