"""Tests for VejaPRO branded HTML email base layout."""

from __future__ import annotations

from app.services.email_html_base import (
    render_branded_email,
    render_code_block,
    render_cta_button,
    render_info_box,
)


def test_render_branded_email_has_html_structure():
    html = render_branded_email(title="Test Email", body_content="<p>Hello</p>")
    assert '<html lang="lt"' in html
    assert "<title>Test Email</title>" in html
    assert "<p>Hello</p>" in html
    assert "</html>" in html


def test_render_branded_email_has_brand_elements():
    html = render_branded_email(title="Brand Test", body_content="<p>X</p>")
    assert "logo.png" in html
    assert "#2d7a50" in html  # primary green
    assert "VejaPRO" in html
    assert "DM Sans" in html


def test_render_branded_email_custom_logo():
    html = render_branded_email(
        title="T",
        body_content="<p>X</p>",
        logo_url="https://cdn.example.com/custom-logo.png",
    )
    assert "https://cdn.example.com/custom-logo.png" in html
    # Default logo path should NOT appear
    assert html.count("logo.png") == 1


def test_render_branded_email_preheader():
    html = render_branded_email(
        title="T",
        body_content="<p>X</p>",
        preheader="Preview text here",
    )
    assert "Preview text here" in html
    assert "display:none" in html  # preheader is hidden


def test_render_branded_email_no_preheader():
    html = render_branded_email(
        title="T",
        body_content="<p>X</p>",
        preheader="",
    )
    # Should not have preheader div when empty
    assert "max-height:0" not in html


def test_render_branded_email_footer_text():
    html = render_branded_email(
        title="T",
        body_content="<p>X</p>",
        footer_text="Custom Footer Line",
    )
    assert "Custom Footer Line" in html
    assert "Visos teis" in html  # copyright line


def test_render_branded_email_has_year():
    from datetime import datetime, timezone

    html = render_branded_email(title="T", body_content="<p>X</p>")
    current_year = str(datetime.now(timezone.utc).year)
    assert current_year in html


def test_render_cta_button_structure():
    html = render_cta_button(url="https://example.com/action", label="Click Me")
    assert "https://example.com/action" in html
    assert "Click Me" in html
    assert "#2d7a50" in html  # default green
    assert 'role="presentation"' in html


def test_render_cta_button_custom_color():
    html = render_cta_button(url="https://example.com", label="Decline", color="#c0392b")
    assert "#c0392b" in html
    assert "Decline" in html


def test_render_info_box():
    html = render_info_box("Important detail here")
    assert "Important detail here" in html
    assert "#f0f5f2" in html  # default highlight bg


def test_render_info_box_custom_bg():
    html = render_info_box("Content", bg_color="#ffe0e0")
    assert "#ffe0e0" in html


def test_render_code_block():
    html = render_code_block("ABC123")
    assert "ABC123" in html
    assert "Courier" in html  # monospace font
    assert "28px" in html  # large font size
