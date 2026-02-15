"""Tests for Supabase Dashboard email template generators."""

from __future__ import annotations

from app.services.email_supabase_templates import (
    generate_supabase_confirmation_template,
    generate_supabase_magic_link_template,
    generate_supabase_reset_password_template,
)


def test_supabase_confirmation_template_structure():
    html = generate_supabase_confirmation_template()
    assert '<html lang="lt"' in html
    assert "VejaPRO" in html
    assert "{{ .ConfirmationURL }}" in html


def test_supabase_confirmation_template_content():
    html = generate_supabase_confirmation_template()
    assert "Patvirtinti" in html
    assert "el. pasto" in html or "el. pasta" in html
    assert "ignoruokite" in html


def test_supabase_confirmation_template_custom_logo():
    html = generate_supabase_confirmation_template(logo_url="https://cdn.test/logo.png")
    assert "https://cdn.test/logo.png" in html


def test_supabase_reset_password_template():
    html = generate_supabase_reset_password_template()
    assert '<html lang="lt"' in html
    assert "{{ .ConfirmationURL }}" in html
    assert "VejaPRO" in html
    assert "slaptazod" in html.lower()
    assert "Atstatyti" in html


def test_supabase_magic_link_template():
    html = generate_supabase_magic_link_template()
    assert '<html lang="lt"' in html
    assert "{{ .ConfirmationURL }}" in html
    assert "VejaPRO" in html
    assert "Prisijungti" in html


def test_all_templates_have_fallback_url():
    """All templates should have a text fallback for the confirmation URL."""
    for gen_fn in [
        generate_supabase_confirmation_template,
        generate_supabase_reset_password_template,
        generate_supabase_magic_link_template,
    ]:
        html = gen_fn()
        # Should have the URL variable at least twice (button + fallback text)
        assert html.count("{{ .ConfirmationURL }}") >= 2, f"{gen_fn.__name__} missing fallback URL"
