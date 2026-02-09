"""Tests for IP allowlist middleware and security headers middleware."""

import os
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import CurrentUser, get_current_user
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.main import _ip_in_allowlist, app
from app.models.project import Base


class IPAllowlistHelperTests(unittest.TestCase):
    """Unit tests for _ip_in_allowlist() helper function."""

    def test_exact_match(self):
        self.assertTrue(_ip_in_allowlist("192.168.1.1", ["192.168.1.1"]))

    def test_exact_no_match(self):
        self.assertFalse(_ip_in_allowlist("10.0.0.1", ["192.168.1.1"]))

    def test_cidr_match(self):
        self.assertTrue(_ip_in_allowlist("192.168.1.100", ["192.168.0.0/16"]))

    def test_cidr_no_match(self):
        self.assertFalse(_ip_in_allowlist("10.0.0.1", ["192.168.0.0/16"]))

    def test_empty_ip(self):
        self.assertFalse(_ip_in_allowlist("", ["192.168.1.1"]))

    def test_invalid_ip(self):
        self.assertFalse(_ip_in_allowlist("not-an-ip", ["192.168.1.1"]))

    def test_empty_allowlist(self):
        self.assertFalse(_ip_in_allowlist("192.168.1.1", []))

    def test_multiple_entries(self):
        allowlist = ["10.0.0.1", "192.168.0.0/24", "172.16.0.0/12"]
        self.assertTrue(_ip_in_allowlist("172.16.5.10", allowlist))
        self.assertFalse(_ip_in_allowlist("8.8.8.8", allowlist))

    def test_cidr_single_host(self):
        self.assertTrue(_ip_in_allowlist("10.10.50.178", ["10.10.50.0/24"]))
        self.assertFalse(_ip_in_allowlist("10.10.51.1", ["10.10.50.0/24"]))


class IPAllowlistMiddlewareTests(unittest.TestCase):
    """Integration tests for admin_ip_allowlist_middleware."""

    def setUp(self):
        get_settings.cache_clear()
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

        self.admin_user = CurrentUser(id=str(uuid.uuid4()), role="ADMIN")

        def override_get_current_user():
            return self.admin_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        get_settings.cache_clear()

    @patch.dict(os.environ, {"ADMIN_IP_ALLOWLIST": ""}, clear=False)
    def test_empty_allowlist_allows_all(self):
        """Empty allowlist means no filtering."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)

    def test_non_admin_routes_unaffected(self):
        """Non-admin routes should pass even with restrictive allowlist."""
        from app.main import settings as app_settings

        original = app_settings.admin_ip_allowlist_raw
        try:
            app_settings.admin_ip_allowlist_raw = "10.0.0.1"
            resp = self.client.get("/health")
            self.assertEqual(resp.status_code, 200)
        finally:
            app_settings.admin_ip_allowlist_raw = original

    def test_admin_route_blocked_returns_404(self):
        """Admin routes from non-allowlisted IP return 404 (not 403)."""
        from app.main import settings as app_settings

        original = app_settings.admin_ip_allowlist_raw
        try:
            # TestClient IP is "testclient" which won't match
            app_settings.admin_ip_allowlist_raw = "10.0.0.1"
            resp = self.client.get("/admin/audit")
            self.assertEqual(resp.status_code, 404)
        finally:
            app_settings.admin_ip_allowlist_raw = original


class SecurityHeadersMiddlewareTests(unittest.TestCase):
    """Tests for security_headers_middleware."""

    def setUp(self):
        get_settings.cache_clear()
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
        get_settings.cache_clear()

    @patch.dict(os.environ, {"SECURITY_HEADERS_ENABLED": "true"}, clear=False)
    def test_all_six_headers_present(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        h = resp.headers
        self.assertEqual(h.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(h.get("X-Frame-Options"), "DENY")
        self.assertEqual(h.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertIn("geolocation=()", h.get("Permissions-Policy", ""))
        self.assertIn("max-age=31536000", h.get("Strict-Transport-Security", ""))
        self.assertIn("default-src", h.get("Content-Security-Policy", ""))

    @patch.dict(os.environ, {"SECURITY_HEADERS_ENABLED": "true"}, clear=False)
    def test_correct_header_values(self):
        resp = self.client.get("/health")
        h = resp.headers
        self.assertEqual(h.get("Permissions-Policy"), "geolocation=(), microphone=(), camera=()")
        self.assertEqual(h.get("Strict-Transport-Security"), "max-age=31536000; includeSubDomains")

    def test_headers_disabled_not_present(self):
        from app.main import settings as app_settings

        original = app_settings.security_headers_enabled
        try:
            app_settings.security_headers_enabled = False
            resp = self.client.get("/health")
            self.assertEqual(resp.status_code, 200)
            # When disabled, middleware-added headers should not be present
            # (some may still be set by route handlers, but not by this middleware)
            self.assertNotIn("Referrer-Policy", resp.headers)
            self.assertNotIn("Permissions-Policy", resp.headers)
        finally:
            app_settings.security_headers_enabled = original

    @patch.dict(os.environ, {"SECURITY_HEADERS_ENABLED": "true"}, clear=False)
    def test_headers_on_api_endpoint(self):
        """Security headers should also appear on API responses."""
        resp = self.client.get("/health")
        self.assertIn("X-Content-Type-Options", resp.headers)
        self.assertIn("Strict-Transport-Security", resp.headers)


if __name__ == "__main__":
    unittest.main()
