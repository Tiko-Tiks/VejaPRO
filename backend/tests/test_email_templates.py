from __future__ import annotations

import pytest

from app.services.email_templates import build_email_payload, build_missing_data_body


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
