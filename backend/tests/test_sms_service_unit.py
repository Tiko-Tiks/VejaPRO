"""
Unit tests for sms_service — SMS sending via Twilio, phone redaction.

Covers:
  - _redact_phone: phone masking (last 3 digits only)
  - send_sms: success path with mock Twilio client
  - send_sms: missing Twilio config raises RuntimeError
  - send_sms: TwilioRestException propagation
  - send_sms: PII redaction in logs
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

# ── Phone Redaction ──────────────────────────────────────────────────


class TestRedactPhone:
    def test_normal_phone(self):
        from app.services.sms_service import _redact_phone

        assert _redact_phone("+37060012345") == "***345"

    def test_short_phone(self):
        from app.services.sms_service import _redact_phone

        assert _redact_phone("12") == "***12"

    def test_exactly_three_digits(self):
        from app.services.sms_service import _redact_phone

        assert _redact_phone("789") == "***789"

    def test_empty_string(self):
        from app.services.sms_service import _redact_phone

        assert _redact_phone("") == ""

    def test_single_char(self):
        from app.services.sms_service import _redact_phone

        assert _redact_phone("5") == "***5"


# ── Send SMS ─────────────────────────────────────────────────────────

_BASE_ENV = {
    "DATABASE_URL": "sqlite:////tmp/test_sms.db",
    "SUPABASE_URL": "https://fake.supabase.co",
    "SUPABASE_KEY": "fake-key",
    "SUPABASE_JWT_SECRET": "super-secret-jwt-key-for-testing-only-32chars",
    "SECRET_KEY": "test-secret-key",
    "ENVIRONMENT": "test",
    "ENABLE_TWILIO": "true",
    "TWILIO_ACCOUNT_SID": "AC_test_sid_123",
    "TWILIO_AUTH_TOKEN": "test_auth_token_456",
    "TWILIO_FROM_NUMBER": "+15005550006",
}


class TestSendSMS:
    def test_send_sms_success(self):
        """Happy path: Twilio client called with correct params."""
        with patch.dict(os.environ, _BASE_ENV, clear=False):
            from app.core.config import get_settings

            get_settings.cache_clear()

            mock_message = MagicMock()
            mock_message.sid = "SM_test_sid_789"

            with patch("app.services.sms_service.Client") as MockClient:
                mock_client_instance = MagicMock()
                mock_client_instance.messages.create.return_value = mock_message
                MockClient.return_value = mock_client_instance

                from app.services.sms_service import send_sms

                sid = send_sms("+37060012345", "Labas, testas!")

                assert sid == "SM_test_sid_789"
                MockClient.assert_called_once_with("AC_test_sid_123", "test_auth_token_456")
                mock_client_instance.messages.create.assert_called_once_with(
                    to="+37060012345",
                    from_="+15005550006",
                    body="Labas, testas!",
                )
            get_settings.cache_clear()

    def test_send_sms_no_config_raises(self):
        """Missing Twilio credentials should raise RuntimeError."""
        env_no_twilio = {
            **_BASE_ENV,
            "TWILIO_ACCOUNT_SID": "",
            "TWILIO_AUTH_TOKEN": "",
            "TWILIO_FROM_NUMBER": "",
        }
        with patch.dict(os.environ, env_no_twilio, clear=False):
            from app.core.config import get_settings

            get_settings.cache_clear()

            from app.services.sms_service import send_sms

            with pytest.raises(RuntimeError, match="Twilio"):
                send_sms("+37060012345", "Test")

            get_settings.cache_clear()

    def test_send_sms_twilio_error_propagates(self):
        """TwilioRestException should propagate to caller."""
        from twilio.base.exceptions import TwilioRestException

        with patch.dict(os.environ, _BASE_ENV, clear=False):
            from app.core.config import get_settings

            get_settings.cache_clear()

            with patch("app.services.sms_service.Client") as MockClient:
                mock_client_instance = MagicMock()
                mock_client_instance.messages.create.side_effect = TwilioRestException(
                    status=400, uri="/test", msg="Invalid phone number"
                )
                MockClient.return_value = mock_client_instance

                from app.services.sms_service import send_sms

                with pytest.raises(TwilioRestException):
                    send_sms("+37060012345", "Test")

            get_settings.cache_clear()

    def test_send_sms_redacts_phone_in_log(self):
        """When PII redaction is on, phone is masked in log messages."""
        env_with_pii = {
            **_BASE_ENV,
            "PII_REDACTION_ENABLED": "true",
        }
        with patch.dict(os.environ, env_with_pii, clear=False):
            from app.core.config import get_settings

            get_settings.cache_clear()

            mock_message = MagicMock()
            mock_message.sid = "SM_test"

            with (
                patch("app.services.sms_service.Client") as MockClient,
                patch("app.services.sms_service.logger") as mock_logger,
            ):
                mock_client_instance = MagicMock()
                mock_client_instance.messages.create.return_value = mock_message
                MockClient.return_value = mock_client_instance

                from app.services.sms_service import send_sms

                send_sms("+37060012345", "Test")

                # Check that logger.info was called with redacted phone
                mock_logger.info.assert_called_once()
                call_args = mock_logger.info.call_args
                # Second positional arg is the to number (redacted)
                assert "***345" in str(call_args)

            get_settings.cache_clear()
