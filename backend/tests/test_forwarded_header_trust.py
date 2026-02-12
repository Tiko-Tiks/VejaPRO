from types import SimpleNamespace

from starlette.datastructures import URL

from app.api.v1.projects import _twilio_request_url as projects_twilio_request_url
from app.api.v1.twilio_voice import _twilio_request_url as voice_twilio_request_url
from app.core.config import get_settings


def _request(
    *,
    peer_ip: str,
    base_url: str = "http://internal.local/api/v1/webhook/twilio/voice",
    forwarded_proto: str | None = None,
    forwarded_host: str | None = None,
):
    headers = {}
    if forwarded_proto is not None:
        headers["x-forwarded-proto"] = forwarded_proto
    if forwarded_host is not None:
        headers["x-forwarded-host"] = forwarded_host
    return SimpleNamespace(
        url=URL(base_url),
        headers=headers,
        client=SimpleNamespace(host=peer_ip),
    )


def test_twilio_request_url_ignores_forwarded_headers_from_untrusted_peer():
    settings = get_settings()
    original_trusted = settings.trusted_proxy_cidrs_raw
    try:
        settings.trusted_proxy_cidrs_raw = "10.0.0.0/8"
        req = _request(
            peer_ip="198.51.100.15",
            forwarded_proto="https",
            forwarded_host="public.example.com",
        )
        expected = "http://internal.local/api/v1/webhook/twilio/voice"
        assert voice_twilio_request_url(req) == expected
        assert projects_twilio_request_url(req) == expected
    finally:
        settings.trusted_proxy_cidrs_raw = original_trusted


def test_twilio_request_url_uses_forwarded_headers_for_trusted_proxy():
    settings = get_settings()
    original_trusted = settings.trusted_proxy_cidrs_raw
    try:
        settings.trusted_proxy_cidrs_raw = "10.0.0.0/8"
        req = _request(
            peer_ip="10.1.2.3",
            forwarded_proto="https",
            forwarded_host="public.example.com",
        )
        expected = "https://public.example.com/api/v1/webhook/twilio/voice"
        assert voice_twilio_request_url(req) == expected
        assert projects_twilio_request_url(req) == expected
    finally:
        settings.trusted_proxy_cidrs_raw = original_trusted
