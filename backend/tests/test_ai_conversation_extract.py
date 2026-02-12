"""Tests for AI Conversation Extract module.

Covers:
- Contracts: ExtractedField validation, AIConversationExtractResult.to_suggestions_dict()
- Service: budget/retry with mock provider, audit log writing
- Endpoint: POST /api/v1/admin/ai/extract-conversation
- Integration: merge_ai_suggestions with operator-priority logic
"""

import asyncio
import json
import os
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import CurrentUser, get_current_user
from app.core.dependencies import get_db
from app.main import app
from app.models.project import AuditLog, Base, CallRequest

# ─── Contract Tests ──────────────────────────────────


class ConversationExtractContractTests(unittest.TestCase):
    """Tests for ExtractedField and AIConversationExtractResult."""

    def test_extracted_field_valid_confidence(self):
        from app.services.ai.conversation_extract.contracts import ExtractedField

        f = ExtractedField(value="Jonas", confidence=0.85)
        self.assertEqual(f.value, "Jonas")
        self.assertEqual(f.confidence, 0.85)

    def test_extracted_field_confidence_too_high(self):
        from pydantic import ValidationError

        from app.services.ai.conversation_extract.contracts import ExtractedField

        with self.assertRaises(ValidationError):
            ExtractedField(value="test", confidence=1.5)

    def test_extracted_field_confidence_negative(self):
        from pydantic import ValidationError

        from app.services.ai.conversation_extract.contracts import ExtractedField

        with self.assertRaises(ValidationError):
            ExtractedField(value="test", confidence=-0.1)

    def test_extracted_field_defaults(self):
        from app.services.ai.conversation_extract.contracts import ExtractedField

        f = ExtractedField()
        self.assertEqual(f.value, "")
        self.assertEqual(f.confidence, 0.0)

    def test_to_suggestions_dict_skips_empty(self):
        from app.services.ai.conversation_extract.contracts import AIConversationExtractResult, ExtractedField

        result = AIConversationExtractResult(
            client_name=ExtractedField(value="Jonas", confidence=0.9),
            phone=ExtractedField(value="", confidence=0.0),
            email=ExtractedField(value="", confidence=0.0),
            address=ExtractedField(value="Gedimino pr. 15", confidence=0.8),
        )
        suggestions = result.to_suggestions_dict()
        self.assertIn("client_name", suggestions)
        self.assertIn("address", suggestions)
        self.assertNotIn("phone", suggestions)
        self.assertNotIn("email", suggestions)

    def test_to_suggestions_dict_includes_all_populated(self):
        from app.services.ai.conversation_extract.contracts import AIConversationExtractResult, ExtractedField

        result = AIConversationExtractResult(
            client_name=ExtractedField(value="Jonas", confidence=0.9),
            phone=ExtractedField(value="+37065512345", confidence=0.85),
            email=ExtractedField(value="jonas@test.lt", confidence=0.8),
            address=ExtractedField(value="Vilnius", confidence=0.7),
            service_type=ExtractedField(value="vejos pjovimas", confidence=0.75),
            urgency=ExtractedField(value="medium", confidence=0.6),
            area_m2=ExtractedField(value="150", confidence=0.5),
        )
        suggestions = result.to_suggestions_dict()
        self.assertEqual(len(suggestions), 7)
        for field_name in ("client_name", "phone", "email", "address", "service_type", "urgency", "area_m2"):
            self.assertIn(field_name, suggestions)
            self.assertIn("value", suggestions[field_name])
            self.assertIn("confidence", suggestions[field_name])


# ─── Service Tests ───────────────────────────────────


class ConversationExtractServiceTests(unittest.TestCase):
    """Tests for extract_conversation_data with mock provider."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    @patch.dict(
        os.environ,
        {
            "AI_CONVERSATION_EXTRACT_PROVIDER": "mock",
            "AI_CONVERSATION_EXTRACT_MODEL": "",
            "AI_CONVERSATION_EXTRACT_TIMEOUT_SECONDS": "5.0",
            "AI_CONVERSATION_EXTRACT_BUDGET_SECONDS": "8.0",
            "AI_CONVERSATION_EXTRACT_MAX_RETRIES": "1",
            "AI_ALLOWED_PROVIDERS": "mock",
            "ENABLE_AI_OVERRIDES": "false",
        },
        clear=False,
    )
    def test_extract_with_mock_returns_fallback(self):
        """Mock provider returns intent-shaped JSON, so extraction falls back to empty."""
        from app.core.config import Settings
        from app.services.ai.conversation_extract.service import extract_conversation_data

        db = self.SessionLocal()
        try:
            with (
                patch("app.services.ai.common.router.get_settings") as mock_gs,
                patch("app.services.ai.common.providers.get_settings") as mock_gs2,
                patch("app.services.ai.common.audit.get_settings") as mock_gs3,
                patch("app.services.ai.conversation_extract.service.get_settings") as mock_gs4,
            ):
                s = Settings()
                mock_gs.return_value = s
                mock_gs2.return_value = s
                mock_gs3.return_value = s
                mock_gs4.return_value = s

                result = asyncio.get_event_loop().run_until_complete(extract_conversation_data("Labas, as Jonas", db))
                db.commit()

                # Mock returns {"intent": "mock", ...} which has no conversation fields,
                # but _parse_extraction handles missing fields — all will be empty.
                self.assertGreaterEqual(result.attempts, 1)
                self.assertGreater(result.total_latency_ms, 0)
                self.assertEqual(result.provider_result.provider, "mock")
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {
            "AI_CONVERSATION_EXTRACT_PROVIDER": "mock",
            "AI_ALLOWED_PROVIDERS": "mock",
            "ENABLE_AI_OVERRIDES": "false",
        },
        clear=False,
    )
    def test_extract_with_patched_response(self):
        """Patch mock to return valid conversation-extract JSON."""
        from app.core.config import Settings
        from app.services.ai.common.providers.base import ProviderResult
        from app.services.ai.conversation_extract.service import extract_conversation_data

        mock_json = json.dumps(
            {
                "client_name": {"value": "Jonas Petraitis", "confidence": 0.95},
                "phone": {"value": "+37065512345", "confidence": 0.9},
                "email": {"value": "", "confidence": 0.0},
                "address": {"value": "Gedimino pr. 15, Vilnius", "confidence": 0.85},
                "service_type": {"value": "vejos pjovimas", "confidence": 0.8},
                "urgency": {"value": "", "confidence": 0.0},
                "area_m2": {"value": "", "confidence": 0.0},
            }
        )

        mock_provider = AsyncMock()
        mock_provider.name = "mock"
        mock_provider.generate.return_value = ProviderResult(raw_text=mock_json, model="test-model", provider="mock")

        db = self.SessionLocal()
        try:
            with (
                patch("app.services.ai.common.router.get_settings") as mock_gs,
                patch("app.services.ai.common.providers.get_settings") as mock_gs2,
                patch("app.services.ai.common.audit.get_settings") as mock_gs3,
                patch("app.services.ai.conversation_extract.service.get_settings") as mock_gs4,
                patch("app.services.ai.common.router.get_provider", return_value=mock_provider),
            ):
                s = Settings()
                mock_gs.return_value = s
                mock_gs2.return_value = s
                mock_gs3.return_value = s
                mock_gs4.return_value = s

                result = asyncio.get_event_loop().run_until_complete(
                    extract_conversation_data("Labas, as Jonas Petraitis, tel 865512345, Gedimino pr 15 Vilnius", db)
                )
                db.commit()

                self.assertEqual(result.extract_result.client_name.value, "Jonas Petraitis")
                self.assertEqual(result.extract_result.client_name.confidence, 0.95)
                self.assertEqual(result.extract_result.phone.value, "+37065512345")
                self.assertEqual(result.extract_result.address.value, "Gedimino pr. 15, Vilnius")
                self.assertEqual(result.extract_result.email.value, "")

                suggestions = result.extract_result.to_suggestions_dict()
                self.assertIn("client_name", suggestions)
                self.assertIn("phone", suggestions)
                self.assertIn("address", suggestions)
                self.assertNotIn("email", suggestions)
        finally:
            db.close()

    @patch.dict(
        os.environ,
        {
            "AI_CONVERSATION_EXTRACT_PROVIDER": "mock",
            "AI_ALLOWED_PROVIDERS": "mock",
        },
        clear=False,
    )
    def test_extract_writes_audit_log(self):
        from app.core.config import Settings
        from app.services.ai.conversation_extract.service import extract_conversation_data

        db = self.SessionLocal()
        try:
            with (
                patch("app.services.ai.common.router.get_settings") as mock_gs,
                patch("app.services.ai.common.providers.get_settings") as mock_gs2,
                patch("app.services.ai.common.audit.get_settings") as mock_gs3,
                patch("app.services.ai.conversation_extract.service.get_settings") as mock_gs4,
            ):
                s = Settings()
                mock_gs.return_value = s
                mock_gs2.return_value = s
                mock_gs3.return_value = s
                mock_gs4.return_value = s

                asyncio.get_event_loop().run_until_complete(
                    extract_conversation_data("test input", db, call_request_id="test-cr-id")
                )
                db.commit()

                logs = db.query(AuditLog).filter(AuditLog.action == "AI_CONVERSATION_EXTRACT").all()
                self.assertGreaterEqual(len(logs), 1)
                log = logs[0]
                self.assertEqual(log.entity_type, "ai")
                self.assertEqual(log.entity_id, "test-cr-id")
                self.assertIn("prompt_hash", log.audit_meta)
        finally:
            db.close()


# ─── Endpoint Tests ──────────────────────────────────


class ConversationExtractEndpointTests(unittest.TestCase):
    """Tests for POST /api/v1/admin/ai/extract-conversation."""

    def setUp(self):
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

        self.current_user = CurrentUser(id=str(uuid.uuid4()), role="ADMIN")

        def override_get_current_user():
            return self.current_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    @patch.dict(
        os.environ,
        {
            "ENABLE_AI_CONVERSATION_EXTRACT": "true",
            "AI_CONVERSATION_EXTRACT_PROVIDER": "mock",
            "AI_ALLOWED_PROVIDERS": "mock",
        },
        clear=False,
    )
    def test_endpoint_success(self):
        resp = self.client.post(
            "/api/v1/admin/ai/extract-conversation",
            json={"text": "Labas, mano vardas Jonas"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("fields", data)
        self.assertIn("provider", data)
        self.assertEqual(data["provider"], "mock")
        self.assertIn("attempts", data)
        self.assertIn("latency_ms", data)

    @patch.dict(os.environ, {"ENABLE_AI_CONVERSATION_EXTRACT": "false"}, clear=False)
    def test_endpoint_disabled_returns_404(self):
        resp = self.client.post(
            "/api/v1/admin/ai/extract-conversation",
            json={"text": "test"},
        )
        self.assertEqual(resp.status_code, 404)

    @patch.dict(
        os.environ,
        {
            "ENABLE_AI_CONVERSATION_EXTRACT": "true",
            "AI_ALLOWED_PROVIDERS": "mock",
        },
        clear=False,
    )
    def test_endpoint_non_admin_returns_403(self):
        self.current_user = CurrentUser(id=str(uuid.uuid4()), role="CLIENT")

        def override_non_admin():
            return self.current_user

        app.dependency_overrides[get_current_user] = override_non_admin
        resp = self.client.post(
            "/api/v1/admin/ai/extract-conversation",
            json={"text": "test"},
        )
        self.assertEqual(resp.status_code, 403)

    @patch.dict(
        os.environ,
        {
            "ENABLE_AI_CONVERSATION_EXTRACT": "true",
            "AI_ALLOWED_PROVIDERS": "mock",
        },
        clear=False,
    )
    def test_endpoint_empty_text_returns_422(self):
        resp = self.client.post(
            "/api/v1/admin/ai/extract-conversation",
            json={"text": ""},
        )
        self.assertEqual(resp.status_code, 422)

    @patch.dict(
        os.environ,
        {
            "ENABLE_AI_CONVERSATION_EXTRACT": "true",
            "AI_CONVERSATION_EXTRACT_PROVIDER": "mock",
            "AI_ALLOWED_PROVIDERS": "mock",
            "AI_CONVERSATION_EXTRACT_MIN_CONFIDENCE": "0.5",
        },
        clear=False,
    )
    def test_endpoint_auto_apply_updates_intake_state(self):
        """Create a CallRequest, extract with auto_apply, verify intake_state updated."""
        from app.services.ai.common.providers.base import ProviderResult

        # Create a call request in the DB
        db = self.SessionLocal()
        cr = CallRequest(
            name="Test",
            phone="865512345",
            status="NEW",
            source="test",
            intake_state={},
        )
        db.add(cr)
        db.commit()
        cr_id = str(cr.id)
        db.close()

        mock_json = json.dumps(
            {
                "client_name": {"value": "Jonas Petraitis", "confidence": 0.95},
                "phone": {"value": "+37065512345", "confidence": 0.9},
                "email": {"value": "", "confidence": 0.0},
                "address": {"value": "Gedimino pr. 15", "confidence": 0.85},
                "service_type": {"value": "", "confidence": 0.0},
                "urgency": {"value": "", "confidence": 0.0},
                "area_m2": {"value": "", "confidence": 0.0},
            }
        )

        mock_provider = AsyncMock()
        mock_provider.name = "mock"
        mock_provider.generate.return_value = ProviderResult(raw_text=mock_json, model="test", provider="mock")

        with patch("app.services.ai.common.router.get_provider", return_value=mock_provider):
            resp = self.client.post(
                "/api/v1/admin/ai/extract-conversation",
                json={"text": "Jonas Petraitis, tel 865512345, Gedimino pr 15", "call_request_id": cr_id},
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(data["applied_count"], 0)

        # Verify intake_state was updated in DB
        db = self.SessionLocal()
        cr = db.get(CallRequest, cr_id)
        q = (cr.intake_state or {}).get("questionnaire", {})
        self.assertEqual(q.get("client_name", {}).get("value"), "Jonas Petraitis")
        self.assertEqual(q.get("client_name", {}).get("source"), "ai")
        self.assertEqual(q.get("phone", {}).get("value"), "+37065512345")
        self.assertEqual(q.get("address", {}).get("value"), "Gedimino pr. 15")
        db.close()


# ─── merge_ai_suggestions Tests ─────────────────────


class MergeAiSuggestionsTests(unittest.TestCase):
    """Tests for merge_ai_suggestions operator-priority logic."""

    def test_merge_operator_never_overwritten(self):
        from app.services.intake_service import merge_ai_suggestions

        state = {
            "questionnaire": {
                "email": {"value": "admin@test.lt", "source": "operator", "confidence": 1.0},
            },
            "workflow": {"row_version": 1},
        }
        suggestions = {"email": {"value": "ai@test.lt", "confidence": 0.95}}
        result = merge_ai_suggestions(state, suggestions, min_confidence=0.5)
        self.assertEqual(result["questionnaire"]["email"]["value"], "admin@test.lt")
        self.assertEqual(result["questionnaire"]["email"]["source"], "operator")

    def test_merge_low_confidence_skipped(self):
        from app.services.intake_service import merge_ai_suggestions

        state = {"questionnaire": {}, "workflow": {"row_version": 1}}
        suggestions = {"email": {"value": "low@test.lt", "confidence": 0.3}}
        result = merge_ai_suggestions(state, suggestions, min_confidence=0.5)
        self.assertNotIn("email", result["questionnaire"])

    def test_merge_applies_high_confidence_to_empty(self):
        from app.services.intake_service import merge_ai_suggestions

        state = {"questionnaire": {}, "workflow": {"row_version": 1}}
        suggestions = {"email": {"value": "good@test.lt", "confidence": 0.8}}
        result = merge_ai_suggestions(state, suggestions, min_confidence=0.5)
        self.assertEqual(result["questionnaire"]["email"]["value"], "good@test.lt")
        self.assertEqual(result["questionnaire"]["email"]["source"], "ai")

    def test_merge_higher_confidence_overwrites_ai(self):
        from app.services.intake_service import merge_ai_suggestions

        state = {
            "questionnaire": {
                "address": {"value": "Senamiestis", "source": "ai", "confidence": 0.6},
            },
            "workflow": {"row_version": 1},
        }
        suggestions = {"address": {"value": "Gedimino pr. 15, Vilnius", "confidence": 0.9}}
        result = merge_ai_suggestions(state, suggestions, min_confidence=0.5)
        self.assertEqual(result["questionnaire"]["address"]["value"], "Gedimino pr. 15, Vilnius")

    def test_merge_lower_confidence_does_not_overwrite(self):
        from app.services.intake_service import merge_ai_suggestions

        state = {
            "questionnaire": {
                "address": {"value": "Gedimino pr. 15", "source": "ai", "confidence": 0.9},
            },
            "workflow": {"row_version": 1},
        }
        suggestions = {"address": {"value": "Kauno g.", "confidence": 0.5}}
        result = merge_ai_suggestions(state, suggestions, min_confidence=0.5)
        self.assertEqual(result["questionnaire"]["address"]["value"], "Gedimino pr. 15")

    def test_urgency_field_accepted(self):
        from app.services.intake_service import merge_ai_suggestions

        state = {"questionnaire": {}, "workflow": {"row_version": 1}}
        suggestions = {"urgency": {"value": "high", "confidence": 0.7}}
        result = merge_ai_suggestions(state, suggestions, min_confidence=0.5)
        self.assertEqual(result["questionnaire"]["urgency"]["value"], "high")

    def test_client_name_field_accepted(self):
        from app.services.intake_service import merge_ai_suggestions

        state = {"questionnaire": {}, "workflow": {"row_version": 1}}
        suggestions = {"client_name": {"value": "Petras", "confidence": 0.9}}
        result = merge_ai_suggestions(state, suggestions, min_confidence=0.5)
        self.assertEqual(result["questionnaire"]["client_name"]["value"], "Petras")

    def test_unknown_field_ignored(self):
        from app.services.intake_service import merge_ai_suggestions

        state = {"questionnaire": {}, "workflow": {"row_version": 1}}
        suggestions = {"unknown_field": {"value": "x", "confidence": 0.9}}
        result = merge_ai_suggestions(state, suggestions, min_confidence=0.5)
        self.assertNotIn("unknown_field", result["questionnaire"])

    def test_whatsapp_consent_ignored(self):
        from app.services.intake_service import merge_ai_suggestions

        state = {"questionnaire": {}, "workflow": {"row_version": 1}}
        suggestions = {"whatsapp_consent": {"value": "true", "confidence": 0.9}}
        result = merge_ai_suggestions(state, suggestions, min_confidence=0.5)
        self.assertNotIn("whatsapp_consent", result["questionnaire"])


if __name__ == "__main__":
    unittest.main()
