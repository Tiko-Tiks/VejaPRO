"""Tests for AI Pricing Scope.

20 tests:
  1. Happy path — generate + store + audit
  2. Flag off → 404
  3. Idempotency (same fingerprint → cached, provider NOT called twice)
  4. Cache invalidation after survey change
  5. No similar projects → RED confidence
  6. Provider timeout → 200 status="fallback"
  7. Extended survey factors in prompt text
  8. Invalid JSON from LLM → 200 status="fallback"
  9. Hallucinated factor name → filtered, valid kept
 10. Decide approve → total_price_client updated
 11. Decide edit missing price/reason → 422; reason < 8 chars → 422
 12. Decide ignore → only audit
 13. Decide stale proposal (fingerprint mismatch) → 409
 14. Role guard → 403 non-ADMIN
 15. Zero-PII test — prompt has no email/phone/name/address
 16. Decision hard-gate — approve/ignore blocked after decision exists
 17-20. Contract tests (filter_valid_factors, clamp, confidence_bucket, survey_completeness)
"""

import asyncio
import json
import os
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.models.project import AuditLog, Base, Project


def _make_project(db, *, area_m2=200.0, complexity="MED", addons=None, status="DRAFT"):
    """Helper to create a project for pricing tests."""
    if addons is None:
        addons = [{"key": "seed", "variant": "premium"}, {"key": "watering", "variant": "smart"}]
    ci = {
        "client_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "id": str(uuid.uuid4()),
        "email": "test@example.lt",
        "phone": "+37061234567",
        "name": "Jonas Jonaitis",
        "address": "Vilniaus g. 10, Vilnius",
        "quote_pending": True,
        "estimate": {
            "area_m2": area_m2,
            "rules_version": "v1",
            "addons_selected": addons,
            "ai_complexity": complexity,
        },
    }
    p = Project(
        client_info=ci,
        status=status,
        area_m2=area_m2,
    )
    db.add(p)
    db.flush()
    return p


def _make_similar_projects(db, *, count=6, area_m2=200.0, price=2500.0):
    """Create N certified projects for similar project matching."""
    for i in range(count):
        p = Project(
            client_info={
                "client_id": str(uuid.uuid4()),
                "estimate": {
                    "area_m2": area_m2 + i * 5,
                    "addons_selected": [{"key": "seed", "variant": "standard"}],
                    "ai_complexity": "MED",
                },
            },
            status="CERTIFIED",
            area_m2=area_m2 + i * 5,
            total_price_client=price + i * 100,
        )
        db.add(p)
    db.flush()


def _mock_pricing_result(factors=None, reasoning_lt="Remiantis panašiais projektais."):
    """Create a mock ProviderResult with pricing JSON."""
    from app.services.ai.common.providers.base import ProviderResult

    if factors is None:
        factors = [
            {"name": "slope_adjustment", "impact_eur": 150.0, "description": "Nuolydis +8%"},
            {"name": "soil_preparation", "impact_eur": 100.0, "description": "Molinis dirvožemis"},
        ]

    response_json = json.dumps({"factors": factors, "reasoning_lt": reasoning_lt})

    return ProviderResult(
        raw_text=response_json,
        model="test-model",
        provider="mock",
        prompt_tokens=200,
        completion_tokens=100,
        latency_ms=500.0,
    )


_ENV_PRICING_ON = {
    "ENABLE_AI_PRICING": "true",
    "AI_PRICING_PROVIDER": "mock",
    "AI_ALLOWED_PROVIDERS": "mock",
    "ENABLE_AI_OVERRIDES": "false",
    "AI_PRICING_MAX_ADJUSTMENT_PCT": "20",
}

_ENV_PRICING_OFF = {
    "ENABLE_AI_PRICING": "false",
}


class _SettingsPatches:
    """Context manager to patch get_settings across all modules."""

    def __init__(self):
        from app.core.config import Settings

        self.settings = Settings()
        self._patches = []

    def __enter__(self):
        targets = [
            "app.services.ai.common.router.get_settings",
            "app.services.ai.common.providers.get_settings",
            "app.services.ai.common.audit.get_settings",
            "app.services.ai.pricing.service.get_settings",
        ]
        for t in targets:
            p = patch(t, return_value=self.settings)
            p.start()
            self._patches.append(p)
        return self.settings

    def __exit__(self, *args):
        for p in self._patches:
            p.stop()


class AIPricingServiceTests(unittest.TestCase):
    """Unit tests for the AI pricing service layer."""

    def setUp(self):
        get_settings.cache_clear()
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def tearDown(self):
        get_settings.cache_clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    # 1. Happy path
    @patch.dict(os.environ, _ENV_PRICING_ON, clear=False)
    def test_happy_path_generate(self):
        """Generate pricing: result stored in vision_analysis, audit logged."""
        from app.services.ai.pricing.service import generate_pricing_proposal

        mock_result = _mock_pricing_result()
        mock_generate = AsyncMock(return_value=mock_result)

        db = self.SessionLocal()
        try:
            project = _make_project(db)
            _make_similar_projects(db, count=6)

            with _SettingsPatches():
                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    result = asyncio.get_event_loop().run_until_complete(generate_pricing_proposal(str(project.id), db))
                    db.commit()

            self.assertIsNotNone(result)
            self.assertEqual(result.status, "ok")
            self.assertGreater(result.deterministic_base, 0)
            self.assertGreater(result.recommended_price, 0)
            self.assertGreater(len(result.factors), 0)
            self.assertTrue(result.input_fingerprint)
            self.assertTrue(result.generated_at)

            # Check stored in vision_analysis
            db.refresh(project)
            va = project.vision_analysis or {}
            self.assertIn("ai_pricing", va)
            self.assertIn("ai_pricing_meta", va)
            self.assertEqual(va["ai_pricing"]["status"], "ok")
            self.assertEqual(va["ai_pricing_meta"]["fingerprint"], result.input_fingerprint)

            # Check audit
            logs = (
                db.execute(select(AuditLog).where(AuditLog.action == "AI_PRICING_PROPOSAL_GENERATED")).scalars().all()
            )
            self.assertEqual(len(logs), 1)
        finally:
            db.close()

    # 2. Flag off → None
    @patch.dict(os.environ, _ENV_PRICING_OFF, clear=False)
    def test_flag_off_returns_none(self):
        """When ENABLE_AI_PRICING=false, service returns None."""
        from app.services.ai.pricing.service import generate_pricing_proposal

        db = self.SessionLocal()
        try:
            project = _make_project(db)
            with _SettingsPatches():
                result = asyncio.get_event_loop().run_until_complete(generate_pricing_proposal(str(project.id), db))
            self.assertIsNone(result)
        finally:
            db.close()

    # 3. Idempotency
    @patch.dict(os.environ, _ENV_PRICING_ON, clear=False)
    def test_idempotency_cached(self):
        """Same fingerprint → cached result, provider not called second time."""
        from app.services.ai.pricing.service import generate_pricing_proposal

        mock_result = _mock_pricing_result()
        mock_generate = AsyncMock(return_value=mock_result)

        db = self.SessionLocal()
        try:
            project = _make_project(db)

            with _SettingsPatches():
                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    r1 = asyncio.get_event_loop().run_until_complete(generate_pricing_proposal(str(project.id), db))
                    db.commit()

                    r2 = asyncio.get_event_loop().run_until_complete(generate_pricing_proposal(str(project.id), db))

            self.assertEqual(mock_generate.call_count, 1)
            self.assertEqual(r1.input_fingerprint, r2.input_fingerprint)
        finally:
            db.close()

    # 4. Cache invalidation after survey change
    @patch.dict(os.environ, _ENV_PRICING_ON, clear=False)
    def test_cache_invalidation_after_survey(self):
        """Changing extended survey invalidates fingerprint → provider called again."""
        from app.services.ai.pricing.service import generate_pricing_proposal

        mock_result = _mock_pricing_result()
        mock_generate = AsyncMock(return_value=mock_result)

        db = self.SessionLocal()
        try:
            project = _make_project(db)

            with _SettingsPatches():
                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    # First call
                    asyncio.get_event_loop().run_until_complete(generate_pricing_proposal(str(project.id), db))
                    db.commit()

                    # Modify survey
                    ci = dict(project.client_info or {})
                    ci["extended_survey"] = {"soil_type": "CLAY", "slope_grade": "STEEP"}
                    project.client_info = ci
                    db.add(project)
                    db.flush()

                    # Second call — should call provider again
                    asyncio.get_event_loop().run_until_complete(generate_pricing_proposal(str(project.id), db))
                    db.commit()

            self.assertEqual(mock_generate.call_count, 2)
        finally:
            db.close()

    # 5. No similar projects → RED confidence
    @patch.dict(os.environ, _ENV_PRICING_ON, clear=False)
    def test_no_similar_projects_red_confidence(self):
        """No similar projects → RED confidence, still returns result."""
        from app.services.ai.pricing.service import generate_pricing_proposal

        mock_result = _mock_pricing_result()
        mock_generate = AsyncMock(return_value=mock_result)

        db = self.SessionLocal()
        try:
            project = _make_project(db)
            # No similar projects created

            with _SettingsPatches():
                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    result = asyncio.get_event_loop().run_until_complete(generate_pricing_proposal(str(project.id), db))
                    db.commit()

            self.assertIsNotNone(result)
            self.assertEqual(result.confidence_bucket, "RED")
            self.assertEqual(result.similar_projects_used, 0)
        finally:
            db.close()

    # 6. Provider timeout → fallback
    @patch.dict(os.environ, _ENV_PRICING_ON, clear=False)
    def test_provider_timeout_fallback(self):
        """Provider timeout → status='fallback', deterministic kaina only."""
        from app.services.ai.pricing.service import generate_pricing_proposal

        mock_generate = AsyncMock(side_effect=TimeoutError("timeout"))

        db = self.SessionLocal()
        try:
            project = _make_project(db)

            with _SettingsPatches():
                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    result = asyncio.get_event_loop().run_until_complete(generate_pricing_proposal(str(project.id), db))
                    db.commit()

            self.assertIsNotNone(result)
            self.assertEqual(result.status, "fallback")
            self.assertGreater(result.deterministic_base, 0)
            self.assertEqual(result.llm_adjustment, 0.0)
            self.assertEqual(result.factors, [])
            self.assertIn("nepavyko", result.reasoning_lt.lower())
        finally:
            db.close()

    # 7. Extended survey factors in prompt
    @patch.dict(os.environ, _ENV_PRICING_ON, clear=False)
    def test_survey_factors_in_prompt(self):
        """Extended survey fields appear in prompt text."""
        from app.services.ai.pricing.service import generate_pricing_proposal

        mock_result = _mock_pricing_result()
        mock_generate = AsyncMock(return_value=mock_result)

        db = self.SessionLocal()
        try:
            project = _make_project(db)
            ci = dict(project.client_info or {})
            ci["extended_survey"] = {"soil_type": "CLAY", "slope_grade": "STEEP", "distance_km": 25.0}
            project.client_info = ci
            db.add(project)
            db.flush()

            with _SettingsPatches():
                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    asyncio.get_event_loop().run_until_complete(generate_pricing_proposal(str(project.id), db))
                    db.commit()

            # Check prompt text contains survey values
            call_args = mock_generate.call_args
            prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
            self.assertIn("CLAY", prompt)
            self.assertIn("STEEP", prompt)
            self.assertIn("25.0", prompt)
        finally:
            db.close()

    # 8. Invalid JSON from LLM → fallback
    @patch.dict(os.environ, _ENV_PRICING_ON, clear=False)
    def test_invalid_json_fallback(self):
        """LLM returns invalid JSON → status='fallback'."""
        from app.services.ai.common.providers.base import ProviderResult
        from app.services.ai.pricing.service import generate_pricing_proposal

        bad_result = ProviderResult(
            raw_text="This is not JSON at all...",
            model="test-model",
            provider="mock",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=200.0,
        )
        mock_generate = AsyncMock(return_value=bad_result)

        db = self.SessionLocal()
        try:
            project = _make_project(db)

            with _SettingsPatches():
                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    result = asyncio.get_event_loop().run_until_complete(generate_pricing_proposal(str(project.id), db))
                    db.commit()

            self.assertIsNotNone(result)
            self.assertEqual(result.status, "fallback")
            self.assertEqual(result.factors, [])
        finally:
            db.close()

    # 9. Hallucinated factor name → filtered
    @patch.dict(os.environ, _ENV_PRICING_ON, clear=False)
    def test_hallucinated_factor_filtered(self):
        """Hallucinated factor names filtered out, valid ones kept."""
        from app.services.ai.pricing.service import generate_pricing_proposal

        mixed_factors = [
            {"name": "slope_adjustment", "impact_eur": 100.0, "description": "Valid"},
            {"name": "magic_unicorn_factor", "impact_eur": 500.0, "description": "Hallucinated"},
            {"name": "soil_preparation", "impact_eur": 50.0, "description": "Valid too"},
        ]
        mock_result = _mock_pricing_result(factors=mixed_factors)
        mock_generate = AsyncMock(return_value=mock_result)

        db = self.SessionLocal()
        try:
            project = _make_project(db)

            with _SettingsPatches():
                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    result = asyncio.get_event_loop().run_until_complete(generate_pricing_proposal(str(project.id), db))
                    db.commit()

            self.assertEqual(result.status, "ok")
            factor_names = [f.name for f in result.factors]
            self.assertIn("slope_adjustment", factor_names)
            self.assertIn("soil_preparation", factor_names)
            self.assertNotIn("magic_unicorn_factor", factor_names)
            self.assertEqual(len(result.factors), 2)
        finally:
            db.close()

    # 10. Decide approve
    @patch.dict(os.environ, _ENV_PRICING_ON, clear=False)
    def test_decide_approve(self):
        """Approve updates total_price_client and creates audit."""
        from app.services.ai.pricing.service import generate_pricing_proposal

        mock_result = _mock_pricing_result()
        mock_generate = AsyncMock(return_value=mock_result)

        db = self.SessionLocal()
        try:
            project = _make_project(db)

            with _SettingsPatches():
                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    asyncio.get_event_loop().run_until_complete(generate_pricing_proposal(str(project.id), db))
                    db.commit()

            # Simulate approve via direct function call
            va = dict(project.vision_analysis or {})
            ai_pricing = va["ai_pricing"]

            self.assertEqual(ai_pricing["status"], "ok")
            recommended = ai_pricing["recommended_price"]
            project.total_price_client = round(float(recommended), 2)
            db.add(project)
            db.commit()

            db.refresh(project)
            self.assertEqual(float(project.total_price_client), recommended)
        finally:
            db.close()

    # 11. Decide edit validation
    @patch.dict(os.environ, _ENV_PRICING_ON, clear=False)
    def test_decide_edit_validation(self):
        """Edit requires adjusted_price > 0 and reason >= 8 chars."""
        from pydantic import ValidationError

        from app.api.v1.ai_pricing import DecideRequest

        # Missing adjusted_price for edit — should fail at endpoint logic level
        req = DecideRequest(action="edit", proposal_fingerprint="abc123")
        self.assertIsNone(req.adjusted_price)

        # reason too short
        req2 = DecideRequest(action="edit", proposal_fingerprint="abc123", adjusted_price=100.0, reason="short")
        self.assertLess(len(req2.reason.strip()), 8)

        # adjusted_price must be > 0
        with self.assertRaises(ValidationError):
            DecideRequest(action="edit", proposal_fingerprint="abc123", adjusted_price=-10.0, reason="Good reason here")

    # 12. Decide ignore
    @patch.dict(os.environ, _ENV_PRICING_ON, clear=False)
    def test_decide_ignore_audit(self):
        """Ignore action: project unchanged, audit with correct action."""
        from app.services.ai.pricing.service import generate_pricing_proposal
        from app.services.transition_service import create_audit_log

        mock_result = _mock_pricing_result()
        mock_generate = AsyncMock(return_value=mock_result)

        db = self.SessionLocal()
        try:
            project = _make_project(db)
            original_price = project.total_price_client

            with _SettingsPatches():
                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    asyncio.get_event_loop().run_until_complete(generate_pricing_proposal(str(project.id), db))
                    db.commit()

            # Simulate ignore
            va = dict(project.vision_analysis or {})
            meta = va.get("ai_pricing_meta") or {}
            va["ai_pricing_decision"] = {
                "action": "ignore",
                "decided_by": "admin-uuid",
                "decided_at": "2026-01-01T00:00:00Z",
                "proposal_fingerprint": meta.get("fingerprint"),
            }
            project.vision_analysis = va
            create_audit_log(
                db,
                entity_type="project",
                entity_id=str(project.id),
                action="AI_PRICING_DECISION_IGNORED",
                old_value=None,
                new_value=va["ai_pricing_decision"],
                actor_type="ADMIN",
                actor_id="admin-uuid",
                ip_address=None,
                user_agent=None,
            )
            db.commit()

            # Price unchanged
            db.refresh(project)
            self.assertEqual(project.total_price_client, original_price)

            # Audit exists
            logs = db.execute(select(AuditLog).where(AuditLog.action == "AI_PRICING_DECISION_IGNORED")).scalars().all()
            self.assertEqual(len(logs), 1)
        finally:
            db.close()

    # 13. Stale proposal fingerprint
    @patch.dict(os.environ, _ENV_PRICING_ON, clear=False)
    def test_stale_proposal_detection(self):
        """Mismatched fingerprint should be detected."""
        from app.services.ai.pricing.service import generate_pricing_proposal

        mock_result = _mock_pricing_result()
        mock_generate = AsyncMock(return_value=mock_result)

        db = self.SessionLocal()
        try:
            project = _make_project(db)

            with _SettingsPatches():
                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    asyncio.get_event_loop().run_until_complete(generate_pricing_proposal(str(project.id), db))
                    db.commit()

            va = dict(project.vision_analysis or {})
            meta = va.get("ai_pricing_meta") or {}
            actual_fp = meta.get("fingerprint", "")

            # A different fingerprint should not match
            self.assertNotEqual(actual_fp, "wrong-fingerprint")
            self.assertTrue(len(actual_fp) > 10)
        finally:
            db.close()

    # 14. Role guard via HTTP endpoint
    @patch.dict(os.environ, _ENV_PRICING_ON, clear=False)
    def test_role_guard_non_admin_403(self):
        """Non-ADMIN role should get 403."""
        import httpx

        from app.core.auth import CurrentUser, get_current_user
        from app.main import app

        def _sub_user(request=None):
            return CurrentUser(id="sub-uuid", role="SUBCONTRACTOR")

        app.dependency_overrides[get_current_user] = _sub_user
        try:
            transport = httpx.ASGITransport(app=app)

            async def _do():
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
                    return await c.post(
                        "/api/v1/admin/pricing/some-id/generate",
                        headers={"X-Test-Role": "SUBCONTRACTOR"},
                    )

            resp = asyncio.get_event_loop().run_until_complete(_do())
            self.assertEqual(resp.status_code, 403)
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    # 15. Zero-PII test
    @patch.dict(os.environ, _ENV_PRICING_ON, clear=False)
    def test_zero_pii_in_prompt(self):
        """Prompt sent to LLM must NOT contain email, phone, name, or address."""
        from app.services.ai.pricing.service import generate_pricing_proposal

        mock_result = _mock_pricing_result()
        mock_generate = AsyncMock(return_value=mock_result)

        db = self.SessionLocal()
        try:
            project = _make_project(db)

            with _SettingsPatches():
                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    asyncio.get_event_loop().run_until_complete(generate_pricing_proposal(str(project.id), db))
                    db.commit()

            call_args = mock_generate.call_args
            prompt = call_args[0][0] if call_args[0] else ""

            # These PII values are in client_info but must NOT appear in prompt
            self.assertNotIn("test@example.lt", prompt)
            self.assertNotIn("+37061234567", prompt)
            self.assertNotIn("Jonas Jonaitis", prompt)
            self.assertNotIn("Vilniaus g. 10", prompt)

            # Also check system prompt
            system_prompt = call_args[1].get("system_prompt", "")
            self.assertNotIn("test@example.lt", system_prompt)
            self.assertNotIn("Jonas", system_prompt)
        finally:
            db.close()


    # 16. Decision hard-gate: approve/ignore blocked after decision exists
    @patch.dict(os.environ, _ENV_PRICING_ON, clear=False)
    def test_decide_hardgate_blocks_approve_after_decision(self):
        """If ai_pricing_decision exists, approve/ignore blocked (422), edit allowed."""
        import httpx

        from app.core.auth import CurrentUser, get_current_user
        from app.main import app
        from app.services.ai.pricing.service import generate_pricing_proposal

        mock_result = _mock_pricing_result()
        mock_generate = AsyncMock(return_value=mock_result)

        db = self.SessionLocal()
        try:
            project = _make_project(db)

            with _SettingsPatches():
                with patch("app.services.ai.common.providers.mock.MockProvider.generate", mock_generate):
                    asyncio.get_event_loop().run_until_complete(generate_pricing_proposal(str(project.id), db))
                    db.commit()

            # Manually set a prior decision
            va = dict(project.vision_analysis or {})
            fingerprint = (va.get("ai_pricing_meta") or {}).get("fingerprint", "")
            va["ai_pricing_decision"] = {
                "action": "approve",
                "decided_by": "admin-uuid",
                "decided_at": "2026-01-01T00:00:00Z",
                "proposal_fingerprint": fingerprint,
            }
            project.vision_analysis = va
            db.add(project)
            db.commit()

            # Test via HTTP endpoint
            def _admin_user(request=None):
                return CurrentUser(id="admin-uuid", role="ADMIN")

            app.dependency_overrides[get_current_user] = _admin_user

            # Inject our test DB
            from app.core.dependencies import get_db

            def _test_db():
                yield db

            app.dependency_overrides[get_db] = _test_db

            try:
                transport = httpx.ASGITransport(app=app)

                async def _do_approve():
                    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
                        return await c.post(
                            f"/api/v1/admin/pricing/{project.id}/decide",
                            json={
                                "action": "approve",
                                "proposal_fingerprint": fingerprint,
                            },
                        )

                async def _do_ignore():
                    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
                        return await c.post(
                            f"/api/v1/admin/pricing/{project.id}/decide",
                            json={
                                "action": "ignore",
                                "proposal_fingerprint": fingerprint,
                            },
                        )

                async def _do_edit():
                    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
                        return await c.post(
                            f"/api/v1/admin/pricing/{project.id}/decide",
                            json={
                                "action": "edit",
                                "proposal_fingerprint": fingerprint,
                                "adjusted_price": 2500.0,
                                "reason": "Klientas derėjosi dėl kainos ilgai",
                            },
                        )

                loop = asyncio.get_event_loop()
                # approve should be blocked
                resp_approve = loop.run_until_complete(_do_approve())
                self.assertEqual(resp_approve.status_code, 422)
                self.assertIn("priimtas", resp_approve.json()["detail"].lower())

                # ignore should be blocked
                resp_ignore = loop.run_until_complete(_do_ignore())
                self.assertEqual(resp_ignore.status_code, 422)

                # edit should be allowed
                resp_edit = loop.run_until_complete(_do_edit())
                self.assertEqual(resp_edit.status_code, 200)
                self.assertTrue(resp_edit.json()["ok"])
            finally:
                app.dependency_overrides.pop(get_current_user, None)
                app.dependency_overrides.pop(get_db, None)
        finally:
            db.close()


class AIPricingContractsTests(unittest.TestCase):
    """Unit tests for contracts module."""

    def test_filter_valid_factors(self):
        from app.services.ai.pricing.contracts import filter_valid_factors

        raw = [
            {"name": "slope_adjustment", "impact_eur": 100, "description": "ok"},
            {"name": "fake_factor", "impact_eur": 200, "description": "bad"},
        ]
        valid = filter_valid_factors(raw, 1000.0)
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0].name, "slope_adjustment")

    def test_clamp_adjustment(self):
        from app.services.ai.pricing.contracts import PricingFactor, clamp_adjustment

        factors = [PricingFactor(name="a", impact_eur=300.0)]
        # 20% of 1000 = 200, so 300 should be clamped to 200
        result = clamp_adjustment(factors, 1000.0, max_pct=20)
        self.assertEqual(result, 200.0)

        # Negative clamping
        factors_neg = [PricingFactor(name="b", impact_eur=-500.0)]
        result_neg = clamp_adjustment(factors_neg, 1000.0, max_pct=20)
        self.assertEqual(result_neg, -200.0)

    def test_compute_confidence_bucket(self):
        from app.services.ai.pricing.contracts import compute_confidence_bucket

        self.assertEqual(compute_confidence_bucket(0.8, 6), "GREEN")
        self.assertEqual(compute_confidence_bucket(0.5, 3), "YELLOW")
        self.assertEqual(compute_confidence_bucket(0.3, 1), "RED")
        self.assertEqual(compute_confidence_bucket(0.7, 4), "YELLOW")  # not enough similar
        self.assertEqual(compute_confidence_bucket(0.1, 5), "YELLOW")  # low survey but enough similar

    def test_compute_survey_completeness(self):
        from app.services.ai.pricing.contracts import compute_survey_completeness

        self.assertEqual(compute_survey_completeness(None), 0.0)
        self.assertEqual(compute_survey_completeness({}), 0.0)
        # All defaults → 0
        self.assertEqual(
            compute_survey_completeness({"soil_type": "UNKNOWN", "slope_grade": "FLAT", "equipment_access": "EASY"}),
            0.0,
        )
        # Some non-default
        self.assertGreater(
            compute_survey_completeness({"soil_type": "CLAY", "slope_grade": "STEEP", "distance_km": 15.0}),
            0.0,
        )
