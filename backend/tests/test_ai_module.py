"""Tests for AI Modulių Testavimo Sistema V5.

Covers:
- Common layer: json_tools, providers factory, router, audit
- Intent scope: contracts validation, service budget/retry, endpoint
- Config: allowlist properties, model validation
"""

import asyncio
import os
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import CurrentUser, get_current_user
from app.core.dependencies import get_db
from app.main import app
from app.models.project import AuditLog, Base


class JsonToolsTests(unittest.TestCase):
    """Tests for app.services.ai.common.json_tools.extract_json."""

    def test_valid_json_object(self):
        from app.services.ai.common.json_tools import extract_json

        result = extract_json('{"intent": "schedule_visit", "confidence": 0.9}')
        self.assertIsInstance(result, dict)
        self.assertEqual(result["intent"], "schedule_visit")

    def test_valid_json_with_prefix(self):
        from app.services.ai.common.json_tools import extract_json

        result = extract_json('Here is the result: {"intent": "cancel", "confidence": 0.8, "params": {}}')
        self.assertIsInstance(result, dict)
        self.assertEqual(result["intent"], "cancel")

    def test_valid_json_array(self):
        from app.services.ai.common.json_tools import extract_json

        result = extract_json("[1, 2, 3]")
        self.assertIsInstance(result, list)
        self.assertEqual(result, [1, 2, 3])

    def test_empty_string_returns_none(self):
        from app.services.ai.common.json_tools import extract_json

        self.assertIsNone(extract_json(""))
        self.assertIsNone(extract_json("   "))

    def test_no_json_returns_none(self):
        from app.services.ai.common.json_tools import extract_json

        self.assertIsNone(extract_json("This is plain text with no JSON"))

    def test_nested_braces(self):
        from app.services.ai.common.json_tools import extract_json

        text = 'prefix {"a": {"b": {"c": 1}}} suffix'
        result = extract_json(text)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["a"]["b"]["c"], 1)

    def test_json_with_escaped_quotes(self):
        from app.services.ai.common.json_tools import extract_json

        text = '{"msg": "He said \\"hello\\""}'
        result = extract_json(text)
        self.assertIsInstance(result, dict)
        self.assertIn("hello", result["msg"])

    def test_invalid_json_returns_none(self):
        from app.services.ai.common.json_tools import extract_json

        self.assertIsNone(extract_json("{invalid json}"))


class ProviderFactoryTests(unittest.TestCase):
    """Tests for provider factory (get_provider)."""

    @patch.dict(os.environ, {"AI_ALLOWED_PROVIDERS": "mock"}, clear=False)
    def test_mock_provider_always_available(self):
        from app.core.config import Settings
        from app.services.ai.common.providers import get_provider
        from app.services.ai.common.providers.mock import MockProvider

        with patch("app.services.ai.common.providers.get_settings") as mock_gs:
            s = Settings()
            mock_gs.return_value = s
            provider = get_provider("mock")
            self.assertIsInstance(provider, MockProvider)

    @patch.dict(os.environ, {"AI_ALLOWED_PROVIDERS": "mock"}, clear=False)
    def test_unknown_provider_falls_back_to_mock(self):
        from app.core.config import Settings
        from app.services.ai.common.providers import get_provider
        from app.services.ai.common.providers.mock import MockProvider

        with patch("app.services.ai.common.providers.get_settings") as mock_gs:
            s = Settings()
            mock_gs.return_value = s
            provider = get_provider("nonexistent_provider")
            self.assertIsInstance(provider, MockProvider)

    @patch.dict(
        os.environ,
        {"AI_ALLOWED_PROVIDERS": "claude,mock", "ANTHROPIC_API_KEY": ""},
        clear=False,
    )
    def test_claude_no_key_falls_back_to_mock(self):
        from app.core.config import Settings
        from app.services.ai.common.providers import get_provider
        from app.services.ai.common.providers.mock import MockProvider

        with patch("app.services.ai.common.providers.get_settings") as mock_gs:
            s = Settings()
            mock_gs.return_value = s
            provider = get_provider("claude")
            self.assertIsInstance(provider, MockProvider)

    @patch.dict(
        os.environ,
        {"AI_ALLOWED_PROVIDERS": "groq,mock", "GROQ_API_KEY": ""},
        clear=False,
    )
    def test_groq_no_key_falls_back_to_mock(self):
        from app.core.config import Settings
        from app.services.ai.common.providers import get_provider
        from app.services.ai.common.providers.mock import MockProvider

        with patch("app.services.ai.common.providers.get_settings") as mock_gs:
            s = Settings()
            mock_gs.return_value = s
            provider = get_provider("groq")
            self.assertIsInstance(provider, MockProvider)

    @patch.dict(
        os.environ,
        {"AI_ALLOWED_PROVIDERS": "openai,mock", "OPENAI_API_KEY": ""},
        clear=False,
    )
    def test_openai_no_key_falls_back_to_mock(self):
        from app.core.config import Settings
        from app.services.ai.common.providers import get_provider
        from app.services.ai.common.providers.mock import MockProvider

        with patch("app.services.ai.common.providers.get_settings") as mock_gs:
            s = Settings()
            mock_gs.return_value = s
            provider = get_provider("openai")
            self.assertIsInstance(provider, MockProvider)


class MockProviderTests(unittest.TestCase):
    """Tests for the mock provider generate method."""

    def test_mock_generate_returns_valid_json(self):
        import json

        from app.services.ai.common.providers.mock import MockProvider

        provider = MockProvider()
        result = asyncio.get_event_loop().run_until_complete(provider.generate("test prompt"))
        self.assertEqual(result.provider, "mock")
        self.assertGreater(len(result.raw_text), 0)
        parsed = json.loads(result.raw_text)
        self.assertIn("intent", parsed)
        self.assertIn("confidence", parsed)

    def test_mock_generate_respects_model_param(self):
        from app.services.ai.common.providers.mock import MockProvider

        provider = MockProvider()
        result = asyncio.get_event_loop().run_until_complete(provider.generate("test", model="custom-model"))
        self.assertEqual(result.model, "custom-model")


class IntentContractTests(unittest.TestCase):
    """Tests for AIIntentResult validation."""

    def test_valid_intent(self):
        from app.services.ai.intent.contracts import AIIntentResult

        r = AIIntentResult(intent="schedule_visit", confidence=0.9, params={})
        self.assertEqual(r.intent, "schedule_visit")

    def test_unknown_intent_rejected(self):
        from pydantic import ValidationError

        from app.services.ai.intent.contracts import AIIntentResult

        with self.assertRaises(ValidationError):
            AIIntentResult(intent="buy_pizza", confidence=0.5, params={})

    def test_confidence_too_high(self):
        from pydantic import ValidationError

        from app.services.ai.intent.contracts import AIIntentResult

        with self.assertRaises(ValidationError):
            AIIntentResult(intent="cancel", confidence=1.5, params={})

    def test_confidence_negative(self):
        from pydantic import ValidationError

        from app.services.ai.intent.contracts import AIIntentResult

        with self.assertRaises(ValidationError):
            AIIntentResult(intent="cancel", confidence=-0.1, params={})

    def test_mock_intent_valid(self):
        from app.services.ai.intent.contracts import AIIntentResult

        r = AIIntentResult(intent="mock", confidence=1.0, params={})
        self.assertEqual(r.intent, "mock")

    def test_all_valid_intents(self):
        from app.services.ai.intent.contracts import VALID_INTENTS, AIIntentResult

        for intent in VALID_INTENTS:
            r = AIIntentResult(intent=intent, confidence=0.5, params={})
            self.assertEqual(r.intent, intent)


class RouterTests(unittest.TestCase):
    """Tests for AI router resolve logic."""

    @patch.dict(
        os.environ,
        {
            "AI_INTENT_PROVIDER": "mock",
            "AI_INTENT_MODEL": "",
            "AI_ALLOWED_PROVIDERS": "mock",
            "ENABLE_AI_OVERRIDES": "false",
        },
        clear=False,
    )
    def test_resolve_intent_default_mock(self):
        from app.core.config import Settings
        from app.services.ai.common.providers.mock import MockProvider
        from app.services.ai.common.router import resolve

        with (
            patch("app.services.ai.common.router.get_settings") as mock_gs,
            patch("app.services.ai.common.providers.get_settings") as mock_gs2,
        ):
            s = Settings()
            mock_gs.return_value = s
            mock_gs2.return_value = s
            config = resolve("intent")
            self.assertIsInstance(config.provider, MockProvider)
            self.assertEqual(config.timeout_seconds, 1.2)

    @patch.dict(
        os.environ,
        {
            "AI_INTENT_PROVIDER": "mock",
            "AI_ALLOWED_PROVIDERS": "mock",
            "ENABLE_AI_OVERRIDES": "true",
        },
        clear=False,
    )
    def test_resolve_override_provider(self):
        from app.core.config import Settings
        from app.services.ai.common.providers.mock import MockProvider
        from app.services.ai.common.router import resolve

        with (
            patch("app.services.ai.common.router.get_settings") as mock_gs,
            patch("app.services.ai.common.providers.get_settings") as mock_gs2,
        ):
            s = Settings()
            mock_gs.return_value = s
            mock_gs2.return_value = s
            config = resolve("intent", override_provider="mock")
            self.assertIsInstance(config.provider, MockProvider)


class IntentServiceTests(unittest.TestCase):
    """Tests for intent service with mock provider."""

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
            "AI_INTENT_PROVIDER": "mock",
            "AI_INTENT_MODEL": "",
            "AI_INTENT_TIMEOUT_SECONDS": "1.2",
            "AI_INTENT_BUDGET_SECONDS": "2.0",
            "AI_INTENT_MAX_RETRIES": "1",
            "AI_ALLOWED_PROVIDERS": "mock",
            "ENABLE_AI_OVERRIDES": "false",
        },
        clear=False,
    )
    def test_parse_intent_with_mock(self):
        from app.core.config import Settings
        from app.services.ai.intent.service import parse_intent

        db = self.SessionLocal()
        try:
            with (
                patch("app.services.ai.common.router.get_settings") as mock_gs,
                patch("app.services.ai.common.providers.get_settings") as mock_gs2,
                patch("app.services.ai.common.audit.get_settings") as mock_gs3,
                patch("app.services.ai.intent.service.get_settings") as mock_gs4,
            ):
                s = Settings()
                mock_gs.return_value = s
                mock_gs2.return_value = s
                mock_gs3.return_value = s
                mock_gs4.return_value = s

                result = asyncio.get_event_loop().run_until_complete(parse_intent("Noriu vizito kita savaite", db))
                db.commit()

                self.assertEqual(result.intent_result.intent, "mock")
                self.assertEqual(result.intent_result.confidence, 1.0)
                self.assertEqual(result.provider_result.provider, "mock")
                self.assertGreaterEqual(result.attempts, 1)
                self.assertGreater(result.total_latency_ms, 0)

                # Check audit log was written
                logs = db.query(AuditLog).filter(AuditLog.action == "AI_INTENT_CLASSIFIED").all()
                self.assertEqual(len(logs), 1)
                self.assertEqual(logs[0].entity_type, "ai")
                # entity_id is a generated UUID (not scope name).
                self.assertIsNotNone(logs[0].entity_id)
        finally:
            db.close()


class AIEndpointTests(unittest.TestCase):
    """Tests for POST /api/v1/admin/ai/parse-intent."""

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
            "ENABLE_AI_INTENT": "true",
            "AI_INTENT_PROVIDER": "mock",
            "AI_ALLOWED_PROVIDERS": "mock",
        },
        clear=False,
    )
    def test_parse_intent_endpoint_success(self):
        resp = self.client.post(
            "/api/v1/admin/ai/parse-intent",
            json={"text": "Noriu užsisakyti vizitą"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("intent", data)
        self.assertIn("confidence", data)
        self.assertIn("provider", data)
        self.assertEqual(data["provider"], "mock")

    @patch.dict(os.environ, {"ENABLE_AI_INTENT": "false"}, clear=False)
    def test_parse_intent_disabled_returns_404(self):
        resp = self.client.post(
            "/api/v1/admin/ai/parse-intent",
            json={"text": "test"},
        )
        self.assertEqual(resp.status_code, 404)

    @patch.dict(
        os.environ,
        {"ENABLE_AI_INTENT": "true", "AI_ALLOWED_PROVIDERS": "mock"},
        clear=False,
    )
    def test_parse_intent_empty_text_returns_422(self):
        resp = self.client.post(
            "/api/v1/admin/ai/parse-intent",
            json={"text": ""},
        )
        self.assertEqual(resp.status_code, 422)

    @patch.dict(
        os.environ,
        {"ENABLE_AI_INTENT": "true", "AI_ALLOWED_PROVIDERS": "mock"},
        clear=False,
    )
    def test_parse_intent_non_admin_returns_403(self):
        self.current_user = CurrentUser(id=str(uuid.uuid4()), role="CLIENT")

        def override_non_admin():
            return self.current_user

        app.dependency_overrides[get_current_user] = override_non_admin
        resp = self.client.post(
            "/api/v1/admin/ai/parse-intent",
            json={"text": "test"},
        )
        self.assertEqual(resp.status_code, 403)

    @patch.dict(
        os.environ,
        {
            "ENABLE_AI_INTENT": "true",
            "AI_INTENT_PROVIDER": "mock",
            "AI_ALLOWED_PROVIDERS": "mock",
        },
        clear=False,
    )
    def test_parse_intent_writes_audit_log(self):
        resp = self.client.post(
            "/api/v1/admin/ai/parse-intent",
            json={"text": "Noriu atšaukti vizitą"},
        )
        self.assertEqual(resp.status_code, 200)

        db = self.SessionLocal()
        try:
            logs = db.query(AuditLog).filter(AuditLog.action == "AI_INTENT_CLASSIFIED").all()
            self.assertGreaterEqual(len(logs), 1)
            log = logs[0]
            self.assertEqual(log.entity_type, "ai")
            # entity_id is a generated UUID (not scope name).
            self.assertIsNotNone(log.entity_id)
            self.assertIn("prompt_hash", log.audit_meta)
            self.assertIn("response_hash", log.audit_meta)
        finally:
            db.close()


class ConfigAIPropertiesTests(unittest.TestCase):
    """Tests for ai_allowed_providers and ai_allowed_models properties."""

    @patch.dict(
        os.environ,
        {"AI_ALLOWED_PROVIDERS": "groq,claude"},
        clear=False,
    )
    def test_allowed_providers_force_mock(self):
        from app.core.config import Settings

        s = Settings()
        providers = s.ai_allowed_providers
        self.assertIn("mock", providers)
        self.assertIn("groq", providers)
        self.assertIn("claude", providers)

    @patch.dict(
        os.environ,
        {"AI_ALLOWED_PROVIDERS": "mock"},
        clear=False,
    )
    def test_allowed_providers_mock_only(self):
        from app.core.config import Settings

        s = Settings()
        providers = s.ai_allowed_providers
        self.assertEqual(providers, ["mock"])

    @patch.dict(
        os.environ,
        {
            "AI_ALLOWED_MODELS_GROQ": "llama-3.1-70b,mixtral-8x7b-32768",
            "AI_ALLOWED_MODELS_CLAUDE": "claude-3-5-haiku-20241022",
        },
        clear=False,
    )
    def test_allowed_models_parsing(self):
        from app.core.config import Settings

        s = Settings()
        models = s.ai_allowed_models
        self.assertEqual(len(models["groq"]), 2)
        self.assertEqual(models["groq"][0], "llama-3.1-70b")
        self.assertEqual(len(models["claude"]), 1)
        self.assertEqual(models["mock"], [])


if __name__ == "__main__":
    unittest.main()
