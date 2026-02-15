from __future__ import annotations

import pytest

from app.services.email_templates import build_email_payload, build_missing_data_body

# ── Existing plain text tests ─────────────────────────────────


def test_final_payment_confirmation_template():
    payload = build_email_payload(
        "FINAL_PAYMENT_CONFIRMATION",
        to="client@example.com",
        token="ABC123",
    )
    assert payload["to"] == "client@example.com"
    assert payload["subject"] == "VejaPRO - Patvirtinkite galutini mokejima"
    assert payload["body_text"] == "Jusu patvirtinimo kodas: ABC123"


def test_offer_email_template():
    payload = build_email_payload(
        "OFFER_EMAIL",
        to="client@example.com",
        slot_start="2026-02-20T10:00:00",
        address="Vilnius",
        confirm_url="https://vejapro.lt/api/v1/public/offer/token/respond",
    )
    assert payload["to"] == "client@example.com"
    assert payload["subject"] == "VejaPRO: Apziuros pasiulymas"
    assert "Data/laikas: 2026-02-20T10:00:00" in payload["body_text"]
    assert "Adresas: Vilnius" in payload["body_text"]
    assert "?action=accept" in payload["body_text"]
    assert "?action=reject" in payload["body_text"]


def test_rescheduled_template():
    payload = build_email_payload(
        "APPOINTMENT_RESCHEDULED",
        to="client@example.com",
        scheduled_at="2026-02-20 10:00",
    )
    assert payload["subject"] == "VejaPRO: vizito laikas pakeistas"
    assert "2026-02-20 10:00" in payload["body_text"]


def test_missing_data_template():
    payload = build_email_payload(
        "EMAIL_AUTO_REPLY_MISSING_DATA",
        to="client@example.com",
        client_name="Jonas",
        missing_fields=["address", "service_type"],
        inbound_subject="Reikia vejos pjovimo",
    )
    assert payload["subject"] == "Re: Reikia vejos pjovimo"
    assert "Sveiki, Jonas" in payload["body_text"]
    assert "paslaugos vietos adresas" in payload["body_text"]
    assert "kokios paslaugos" in payload["body_text"]


def test_missing_data_body_helper_defaults_name():
    body = build_missing_data_body("", ["phone"])
    assert "Sveiki, Kliente" in body
    assert "telefono numeris" in body


def test_unknown_template_raises():
    with pytest.raises(ValueError, match="Unknown email template"):
        build_email_payload("UNKNOWN_TEMPLATE", to="x@example.com")


# ── HTML body tests ───────────────────────────────────────────


def _assert_is_branded_html(html: str) -> None:
    """Common assertions for all branded HTML email bodies."""
    assert '<html lang="lt"' in html
    assert "VejaPRO" in html
    assert "#2d7a50" in html
    assert "logo.png" in html


def test_final_payment_confirmation_html():
    payload = build_email_payload(
        "FINAL_PAYMENT_CONFIRMATION",
        to="client@example.com",
        token="XYZ789",
    )
    assert "body_html" in payload
    html = payload["body_html"]
    _assert_is_branded_html(html)
    assert "XYZ789" in html
    assert "Courier" in html  # monospace code block


def test_appointment_rescheduled_html():
    payload = build_email_payload(
        "APPOINTMENT_RESCHEDULED",
        to="client@example.com",
        scheduled_at="2026-03-15 14:30",
    )
    assert "body_html" in payload
    html = payload["body_html"]
    _assert_is_branded_html(html)
    assert "2026-03-15 14:30" in html


def test_offer_email_html():
    payload = build_email_payload(
        "OFFER_EMAIL",
        to="client@example.com",
        slot_start="2026-03-20T09:00:00",
        address="Kaunas, Laisves al. 5",
        confirm_url="https://vejapro.lt/api/v1/public/offer/tok123/respond",
    )
    assert "body_html" in payload
    html = payload["body_html"]
    _assert_is_branded_html(html)
    assert "2026-03-20T09:00:00" in html
    assert "Kaunas" in html
    assert "action=accept" in html
    assert "action=reject" in html
    assert "Patvirtinti" in html
    assert "Atsisakyti" in html


def test_missing_data_html():
    payload = build_email_payload(
        "EMAIL_AUTO_REPLY_MISSING_DATA",
        to="client@example.com",
        client_name="Petras",
        missing_fields=["phone", "address"],
        inbound_subject="Uzklausimas",
    )
    assert "body_html" in payload
    html = payload["body_html"]
    _assert_is_branded_html(html)
    assert "Petras" in html
    assert "telefono" in html
    assert "adresas" in html


def test_client_portal_access_html():
    payload = build_email_payload(
        "CLIENT_PORTAL_ACCESS",
        to="client@example.com",
        portal_url="https://vejapro.lt/client?token=abc123",
        client_name="Ona",
    )
    assert "body_html" in payload
    html = payload["body_html"]
    _assert_is_branded_html(html)
    assert "Ona" in html
    assert "https://vejapro.lt/client?token=abc123" in html
    assert "Prisijungti" in html
    assert "7 dien" in html


def test_all_templates_have_both_text_and_html():
    """Every template must return both body_text and body_html."""
    test_cases = [
        ("FINAL_PAYMENT_CONFIRMATION", {"token": "TEST"}),
        ("APPOINTMENT_RESCHEDULED", {"scheduled_at": "2026-01-01 10:00"}),
        ("OFFER_EMAIL", {"slot_start": "2026-01-01T10:00", "address": "Test", "confirm_url": "https://t.co/x"}),
        ("EMAIL_AUTO_REPLY_MISSING_DATA", {"missing_fields": ["phone"], "client_name": "T", "inbound_subject": "S"}),
        ("CLIENT_PORTAL_ACCESS", {"portal_url": "https://t.co/portal", "client_name": "T"}),
    ]
    for template_key, ctx in test_cases:
        payload = build_email_payload(template_key, to="test@example.com", **ctx)
        assert "body_text" in payload, f"{template_key} missing body_text"
        assert "body_html" in payload, f"{template_key} missing body_html"
        assert len(payload["body_text"]) > 0, f"{template_key} has empty body_text"
        assert len(payload["body_html"]) > 0, f"{template_key} has empty body_html"


def test_html_escapes_special_characters():
    """HTML content should escape user-provided values."""
    payload = build_email_payload(
        "CLIENT_PORTAL_ACCESS",
        to="test@example.com",
        portal_url="https://example.com/?a=1&b=2",
        client_name='<script>alert("xss")</script>',
    )
    html = payload["body_html"]
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&amp;" in html
