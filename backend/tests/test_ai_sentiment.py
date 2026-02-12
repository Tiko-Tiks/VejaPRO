"""Tests for AI Email Sentiment Classification.

Covers:
- Happy path: NEGATIVE classification with audit
- Retry idempotency: same message_id → no second AI call
- Timeout graceful degradation: provider failure → None
- Feature flag OFF → None
- No message_id → classifies, source_message_id=None
- NEUTRAL enforces empty reason_codes
- Message-Id normalization (whitespace tolerance)
- CAS concurrency simulation
"""

import asyncio
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.models.project import AuditLog, Base, CallRequest
from app.schemas.assistant import CallRequestStatus
from app.services.intake_service import _get_intake_state


def _make_cr(db, *, email="jonas@example.lt", name="Jonas"):
    """Helper to create a CallRequest for testing."""
    cr = CallRequest(
        name=name,
        phone="",
        email=email,
        notes="Test notes",
        status=CallRequestStatus.NEW.value,
        source="email",
        intake_state={},
    )
    db.add(cr)
    db.flush()
    return cr


def _mock_provider_result(label="NEGATIVE", confidence=0.92, reason_codes=None):
    """Create a mock ProviderResult with sentiment JSON."""
    from app.services.ai.common.providers.base import ProviderResult

    if reason_codes is None:
        reason_codes = ["FRUSTRATION", "DELAY"]

    response_json = json.dumps(
        {
            "label": label,
            "confidence": confidence,
            "reason_codes": reason_codes,
        }
    )

    return ProviderResult(
        raw_text=response_json,
        model="test-model",
        provider="mock",
        prompt_tokens=100,
        completion_tokens=50,
        latency_ms=150.0,
    )


class SentimentServiceTests(unittest.TestCase):
    """Tests for classify_email_sentiment."""

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

    @patch.dict(
        os.environ,
        {
            "ENABLE_AI_EMAIL_SENTIMENT": "true",
            "AI_SENTIMENT_PROVIDER": "mock",
            "AI_ALLOWED_PROVIDERS": "mock",
            "ENABLE_AI_OVERRIDES": "false",
        },
        clear=False,
    )
    def test_happy_path_negative(self):
        """NEGATIVE classification: result written to intake_state, audit logged."""
        from app.core.config import Settings
        from app.services.ai.sentiment.service import classify_email_sentiment

        mock_result = _mock_provider_result("NEGATIVE", 0.92, ["FRUSTRATION", "DELAY"])
        mock_generate = AsyncMock(return_value=mock_result)

        db = self.SessionLocal()
        try:
            cr = _make_cr(db)

            with (
                patch("app.services.ai.common.router.get_settings") as mock_gs1,
                patch("app.services.ai.common.providers.get_settings") as mock_gs2,
                patch("app.services.ai.common.audit.get_settings") as mock_gs3,
                patch("app.services.ai.sentiment.service.get_settings") as mock_gs4,
            ):
                s = Settings()
                mock_gs1.return_value = s
                mock_gs2.return_value = s
                mock_gs3.return_value = s
                mock_gs4.return_value = s

                # Patch the mock provider's generate method
                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    result = asyncio.get_event_loop().run_until_complete(
                        classify_email_sentiment(
                            "Labas, jūsų paslauga labai bloga!",
                            db,
                            call_request_id=str(cr.id),
                            message_id="<test123@example.lt>",
                        )
                    )
                    db.commit()

            self.assertIsNotNone(result)
            self.assertEqual(result.label, "NEGATIVE")
            self.assertAlmostEqual(result.confidence, 0.92, places=2)
            self.assertEqual(result.reason_codes, ["FRUSTRATION", "DELAY"])

            # Check intake_state was updated
            db.refresh(cr)
            state = _get_intake_state(cr)
            sa = state.get("sentiment_analysis", {})
            self.assertEqual(sa["label"], "NEGATIVE")
            self.assertAlmostEqual(sa["confidence"], 0.92, places=2)
            self.assertEqual(sa["reason_codes"], ["FRUSTRATION", "DELAY"])
            self.assertEqual(sa["source_message_id"], "<test123@example.lt>")
            self.assertEqual(sa["provider"], "mock")
            self.assertIsInstance(sa["latency_ms"], int)
            self.assertTrue(sa["classified_at"].startswith("2026") or sa["classified_at"].startswith("20"))

            # Check audit log was created with correct action
            logs = (
                db.execute(select(AuditLog).where(AuditLog.action == "AI_EMAIL_SENTIMENT_CLASSIFIED")).scalars().all()
            )
            self.assertEqual(len(logs), 1)
            self.assertEqual(str(logs[0].entity_id), str(cr.id))
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {
            "ENABLE_AI_EMAIL_SENTIMENT": "true",
            "AI_SENTIMENT_PROVIDER": "mock",
            "AI_ALLOWED_PROVIDERS": "mock",
            "ENABLE_AI_OVERRIDES": "false",
        },
        clear=False,
    )
    def test_retry_idempotency(self):
        """Same message_id → no second AI call, returns cached."""
        from app.core.config import Settings
        from app.services.ai.sentiment.service import classify_email_sentiment

        mock_result = _mock_provider_result("NEGATIVE", 0.85, ["PRICING"])
        mock_generate = AsyncMock(return_value=mock_result)

        db = self.SessionLocal()
        try:
            cr = _make_cr(db)

            with (
                patch("app.services.ai.common.router.get_settings") as mock_gs1,
                patch("app.services.ai.common.providers.get_settings") as mock_gs2,
                patch("app.services.ai.common.audit.get_settings") as mock_gs3,
                patch("app.services.ai.sentiment.service.get_settings") as mock_gs4,
            ):
                s = Settings()
                mock_gs1.return_value = s
                mock_gs2.return_value = s
                mock_gs3.return_value = s
                mock_gs4.return_value = s

                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    # First call — should classify
                    result1 = asyncio.get_event_loop().run_until_complete(
                        classify_email_sentiment(
                            "Kaina per didelė!",
                            db,
                            call_request_id=str(cr.id),
                            message_id="<dedup123@example.lt>",
                        )
                    )
                    db.commit()

                    self.assertIsNotNone(result1)
                    self.assertEqual(mock_generate.call_count, 1)

                    # Second call with same message_id — should return cached, NOT call provider
                    result2 = asyncio.get_event_loop().run_until_complete(
                        classify_email_sentiment(
                            "Kaina per didelė!",
                            db,
                            call_request_id=str(cr.id),
                            message_id="<dedup123@example.lt>",
                        )
                    )

                    self.assertIsNotNone(result2)
                    self.assertEqual(result2.label, "NEGATIVE")
                    # Provider should NOT have been called a second time
                    self.assertEqual(mock_generate.call_count, 1)
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {
            "ENABLE_AI_EMAIL_SENTIMENT": "true",
            "AI_SENTIMENT_PROVIDER": "mock",
            "AI_ALLOWED_PROVIDERS": "mock",
            "ENABLE_AI_OVERRIDES": "false",
        },
        clear=False,
    )
    def test_timeout_graceful_degrade(self):
        """Provider raises exception → returns None, CR unchanged."""
        from app.core.config import Settings
        from app.services.ai.sentiment.service import classify_email_sentiment

        mock_generate = AsyncMock(side_effect=TimeoutError("Provider timeout"))

        db = self.SessionLocal()
        try:
            cr = _make_cr(db)

            with (
                patch("app.services.ai.common.router.get_settings") as mock_gs1,
                patch("app.services.ai.common.providers.get_settings") as mock_gs2,
                patch("app.services.ai.sentiment.service.get_settings") as mock_gs3,
            ):
                s = Settings()
                mock_gs1.return_value = s
                mock_gs2.return_value = s
                mock_gs3.return_value = s

                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    result = asyncio.get_event_loop().run_until_complete(
                        classify_email_sentiment(
                            "Noriu paslaugos",
                            db,
                            call_request_id=str(cr.id),
                            message_id="<timeout@example.lt>",
                        )
                    )

            self.assertIsNone(result)

            # CR should be unchanged
            db.refresh(cr)
            state = _get_intake_state(cr)
            self.assertNotIn("sentiment_analysis", state)
        finally:
            db.close()

    @patch.dict(os.environ, {"ENABLE_AI_EMAIL_SENTIMENT": "false"}, clear=False)
    def test_flag_off(self):
        """ENABLE_AI_EMAIL_SENTIMENT=false → returns None, provider not called."""
        from app.services.ai.sentiment.service import classify_email_sentiment

        db = self.SessionLocal()
        try:
            cr = _make_cr(db)

            with patch("app.services.ai.sentiment.service.get_settings") as mock_gs:
                from app.core.config import Settings

                mock_gs.return_value = Settings()

                result = asyncio.get_event_loop().run_until_complete(
                    classify_email_sentiment(
                        "Labas",
                        db,
                        call_request_id=str(cr.id),
                        message_id="<flag@example.lt>",
                    )
                )

            self.assertIsNone(result)
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {
            "ENABLE_AI_EMAIL_SENTIMENT": "true",
            "AI_SENTIMENT_PROVIDER": "mock",
            "AI_ALLOWED_PROVIDERS": "mock",
            "ENABLE_AI_OVERRIDES": "false",
        },
        clear=False,
    )
    def test_no_message_id(self):
        """message_id=None → classifies, source_message_id=None in state."""
        from app.core.config import Settings
        from app.services.ai.sentiment.service import classify_email_sentiment

        mock_result = _mock_provider_result("NEUTRAL", 0.7, [])
        mock_generate = AsyncMock(return_value=mock_result)

        db = self.SessionLocal()
        try:
            cr = _make_cr(db)

            with (
                patch("app.services.ai.common.router.get_settings") as mock_gs1,
                patch("app.services.ai.common.providers.get_settings") as mock_gs2,
                patch("app.services.ai.common.audit.get_settings") as mock_gs3,
                patch("app.services.ai.sentiment.service.get_settings") as mock_gs4,
            ):
                s = Settings()
                mock_gs1.return_value = s
                mock_gs2.return_value = s
                mock_gs3.return_value = s
                mock_gs4.return_value = s

                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    result = asyncio.get_event_loop().run_until_complete(
                        classify_email_sentiment(
                            "Noriu vejos pjovimo paslaugos",
                            db,
                            call_request_id=str(cr.id),
                            message_id=None,
                        )
                    )
                    db.commit()

            self.assertIsNotNone(result)
            self.assertEqual(result.label, "NEUTRAL")

            # source_message_id should be None
            db.refresh(cr)
            state = _get_intake_state(cr)
            sa = state.get("sentiment_analysis", {})
            self.assertIsNone(sa["source_message_id"])
            self.assertEqual(sa["label"], "NEUTRAL")
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {
            "ENABLE_AI_EMAIL_SENTIMENT": "true",
            "AI_SENTIMENT_PROVIDER": "mock",
            "AI_ALLOWED_PROVIDERS": "mock",
            "ENABLE_AI_OVERRIDES": "false",
        },
        clear=False,
    )
    def test_neutral_enforces_empty_reason_codes(self):
        """Provider returns reason_codes for NEUTRAL → service clears them."""
        from app.core.config import Settings
        from app.services.ai.sentiment.service import classify_email_sentiment

        # Provider incorrectly returns reason_codes for NEUTRAL
        mock_result = _mock_provider_result("NEUTRAL", 0.8, ["DELAY", "PRICING"])
        mock_generate = AsyncMock(return_value=mock_result)

        db = self.SessionLocal()
        try:
            cr = _make_cr(db)

            with (
                patch("app.services.ai.common.router.get_settings") as mock_gs1,
                patch("app.services.ai.common.providers.get_settings") as mock_gs2,
                patch("app.services.ai.common.audit.get_settings") as mock_gs3,
                patch("app.services.ai.sentiment.service.get_settings") as mock_gs4,
            ):
                s = Settings()
                mock_gs1.return_value = s
                mock_gs2.return_value = s
                mock_gs3.return_value = s
                mock_gs4.return_value = s

                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    result = asyncio.get_event_loop().run_until_complete(
                        classify_email_sentiment(
                            "Viskas gerai, ačiū",
                            db,
                            call_request_id=str(cr.id),
                            message_id="<neutral@example.lt>",
                        )
                    )
                    db.commit()

            self.assertIsNotNone(result)
            self.assertEqual(result.label, "NEUTRAL")
            self.assertEqual(result.reason_codes, [])  # Enforced to empty

            # Check in state too
            db.refresh(cr)
            state = _get_intake_state(cr)
            sa = state.get("sentiment_analysis", {})
            self.assertEqual(sa["reason_codes"], [])
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {
            "ENABLE_AI_EMAIL_SENTIMENT": "true",
            "AI_SENTIMENT_PROVIDER": "mock",
            "AI_ALLOWED_PROVIDERS": "mock",
            "ENABLE_AI_OVERRIDES": "false",
        },
        clear=False,
    )
    def test_message_id_normalization(self):
        """Call with '<abc@x>', then ' <abc@x> ' (whitespace) → idempotent."""
        from app.core.config import Settings
        from app.services.ai.sentiment.service import classify_email_sentiment

        mock_result = _mock_provider_result("POSITIVE", 0.95, [])
        mock_generate = AsyncMock(return_value=mock_result)

        db = self.SessionLocal()
        try:
            cr = _make_cr(db)

            with (
                patch("app.services.ai.common.router.get_settings") as mock_gs1,
                patch("app.services.ai.common.providers.get_settings") as mock_gs2,
                patch("app.services.ai.common.audit.get_settings") as mock_gs3,
                patch("app.services.ai.sentiment.service.get_settings") as mock_gs4,
            ):
                s = Settings()
                mock_gs1.return_value = s
                mock_gs2.return_value = s
                mock_gs3.return_value = s
                mock_gs4.return_value = s

                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    # First call with clean message_id
                    result1 = asyncio.get_event_loop().run_until_complete(
                        classify_email_sentiment(
                            "Ačiū už puikią paslaugą!",
                            db,
                            call_request_id=str(cr.id),
                            message_id="<norm@example.lt>",
                        )
                    )
                    db.commit()

                    self.assertIsNotNone(result1)
                    self.assertEqual(mock_generate.call_count, 1)

                    # Second call with whitespace around same message_id
                    result2 = asyncio.get_event_loop().run_until_complete(
                        classify_email_sentiment(
                            "Ačiū už puikią paslaugą!",
                            db,
                            call_request_id=str(cr.id),
                            message_id="  <norm@example.lt>  ",
                        )
                    )

                    self.assertIsNotNone(result2)
                    # Provider should NOT have been called a second time
                    self.assertEqual(mock_generate.call_count, 1)
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {
            "ENABLE_AI_EMAIL_SENTIMENT": "true",
            "AI_SENTIMENT_PROVIDER": "mock",
            "AI_ALLOWED_PROVIDERS": "mock",
            "ENABLE_AI_OVERRIDES": "false",
        },
        clear=False,
    )
    def test_cas_concurrency_simulation(self):
        """Simulate: between AI call and write, another process wrote sentiment."""
        from app.core.config import Settings
        from app.services.ai.sentiment.service import classify_email_sentiment

        mock_result = _mock_provider_result("NEGATIVE", 0.88, ["RUDENESS"])
        mock_generate = AsyncMock(return_value=mock_result)

        db = self.SessionLocal()
        try:
            cr = _make_cr(db)

            # Pre-set sentiment (simulating another concurrent process already wrote it)
            state = dict(cr.intake_state or {})
            state["sentiment_analysis"] = {
                "label": "NEGATIVE",
                "confidence": 0.90,
                "reason_codes": ["FRUSTRATION"],
                "source_message_id": "<cas@example.lt>",
                "model": "earlier-model",
                "provider": "mock",
                "latency_ms": 200,
                "classified_at": "2026-02-12T09:00:00Z",
            }
            cr.intake_state = state
            db.add(cr)
            db.commit()

            with (
                patch("app.services.ai.common.router.get_settings") as mock_gs1,
                patch("app.services.ai.common.providers.get_settings") as mock_gs2,
                patch("app.services.ai.common.audit.get_settings") as mock_gs3,
                patch("app.services.ai.sentiment.service.get_settings") as mock_gs4,
            ):
                s = Settings()
                mock_gs1.return_value = s
                mock_gs2.return_value = s
                mock_gs3.return_value = s
                mock_gs4.return_value = s

                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    # This call should detect that sentiment was already written for this message_id
                    # via the pre-call idempotency check and return cached without calling provider
                    result = asyncio.get_event_loop().run_until_complete(
                        classify_email_sentiment(
                            "Kodėl taip blogai?!",
                            db,
                            call_request_id=str(cr.id),
                            message_id="<cas@example.lt>",
                        )
                    )

            self.assertIsNotNone(result)
            self.assertEqual(result.label, "NEGATIVE")
            # Provider should NOT have been called (idempotency)
            self.assertEqual(mock_generate.call_count, 0)

            # State should be unchanged (the earlier write should persist)
            db.refresh(cr)
            sa = _get_intake_state(cr).get("sentiment_analysis", {})
            self.assertEqual(sa["confidence"], 0.90)
            self.assertEqual(sa["reason_codes"], ["FRUSTRATION"])
            self.assertEqual(sa["model"], "earlier-model")

            # No additional audit logs should have been created
            logs = (
                db.execute(select(AuditLog).where(AuditLog.action == "AI_EMAIL_SENTIMENT_CLASSIFIED")).scalars().all()
            )
            self.assertEqual(len(logs), 0)
        finally:
            db.close()
