"""
VejaPRO Branded HTML Email Base Layout

Table-based, inline-CSS HTML email wrapper matching VejaPRO brand identity.
Compatible with: Outlook, Gmail, Yahoo, Apple Mail.

Usage:
    from app.services.email_html_base import render_branded_email

    html = render_branded_email(
        title="Mokejimo patvirtinimas",
        body_content="<p>Jusu patvirtinimo kodas: <strong>ABC123</strong></p>",
        preheader="Jusu patvirtinimo kodas: ABC123",
    )
"""

from __future__ import annotations

from datetime import datetime, timezone

# ── Brand tokens ──────────────────────────────────────────────
COLOR_PRIMARY = "#2d7a50"
COLOR_PRIMARY_DARK = "#1e5c3a"
COLOR_ACCENT = "#b8912e"
COLOR_BG = "#faf9f6"
COLOR_WHITE = "#ffffff"
COLOR_BORDER = "#e2ddd5"
COLOR_TEXT = "#1a1a1a"
COLOR_MUTED = "#5a5a5a"
COLOR_HIGHLIGHT_BG = "#f0f5f2"

FONT_STACK = "'DM Sans', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"

DEFAULT_LOGO_PATH = "/static/logo.png"
DEFAULT_FOOTER = "VejaPRO \u2013 Profesionalios vejos prie\u017ei\u016bros paslaugos"


def _get_logo_url(logo_url: str) -> str:
    """Resolve logo URL, falling back to public_base_url + /static/logo.png."""
    if logo_url:
        return logo_url
    try:
        from app.core.config import get_settings

        settings = get_settings()
        base = (settings.public_base_url or "https://vejapro.lt").rstrip("/")
    except Exception:
        base = "https://vejapro.lt"
    return f"{base}{DEFAULT_LOGO_PATH}"


def render_branded_email(
    *,
    title: str,
    body_content: str,
    preheader: str = "",
    logo_url: str = "",
    footer_text: str = DEFAULT_FOOTER,
) -> str:
    """Render body_content inside VejaPRO branded HTML email layout.

    Args:
        title: Email title (used in <title> and optional heading).
        body_content: Inner HTML content for the specific template.
        preheader: Hidden preview text shown by email clients.
        logo_url: Full URL to logo image. Defaults to public_base_url/static/logo.png.
        footer_text: Footer tagline text.

    Returns:
        Complete HTML string ready for email sending.
    """
    resolved_logo = _get_logo_url(logo_url)
    year = datetime.now(timezone.utc).year

    # Preheader trick: hidden text that shows in email client preview
    preheader_html = ""
    if preheader:
        preheader_html = (
            f'<div style="display:none;font-size:1px;color:{COLOR_BG};line-height:1px;'
            f'max-height:0;max-width:0;opacity:0;overflow:hidden;">'
            f"{preheader}"
            f"</div>"
        )

    return f"""\
<!DOCTYPE html>
<html lang="lt" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <title>{title}</title>
  <!--[if mso]>
  <noscript>
    <xml>
      <o:OfficeDocumentSettings>
        <o:PixelsPerInch>96</o:PixelsPerInch>
      </o:OfficeDocumentSettings>
    </xml>
  </noscript>
  <![endif]-->
</head>
<body style="margin:0;padding:0;background-color:{COLOR_BG};font-family:{FONT_STACK};-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">
{preheader_html}

<!-- Outer wrapper -->
<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color:{COLOR_BG};">
  <tr>
    <td align="center" style="padding:24px 16px;">

      <!-- Inner container (600px) -->
      <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width:600px;width:100%;background-color:{COLOR_WHITE};border:1px solid {COLOR_BORDER};border-radius:12px;overflow:hidden;">

        <!-- Header with logo -->
        <tr>
          <td align="center" style="padding:28px 32px 20px 32px;border-bottom:3px solid {COLOR_PRIMARY};">
            <img src="{resolved_logo}" alt="VejaPRO" width="140" style="display:block;max-width:140px;height:auto;border:0;" />
          </td>
        </tr>

        <!-- Body content -->
        <tr>
          <td style="padding:32px 32px 28px 32px;color:{COLOR_TEXT};font-family:{FONT_STACK};font-size:15px;line-height:1.6;">
{body_content}
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:20px 32px;background-color:{COLOR_BG};border-top:1px solid {COLOR_BORDER};text-align:center;font-family:{FONT_STACK};font-size:12px;color:{COLOR_MUTED};line-height:1.5;">
            {footer_text}<br />
            &copy; {year} VejaPRO. Visos teis\u0117s saugomos.
          </td>
        </tr>

      </table>
      <!-- /Inner container -->

    </td>
  </tr>
</table>
<!-- /Outer wrapper -->

</body>
</html>"""


def render_cta_button(*, url: str, label: str, color: str = COLOR_PRIMARY) -> str:
    """Render a CTA button compatible with Outlook and all major email clients.

    Uses table-based layout for maximum compatibility.
    """
    return (
        f'<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:20px auto;">'
        f"<tr>"
        f'<td align="center" style="border-radius:6px;background:{color};">'
        f'<a href="{url}" target="_blank" '
        f'style="display:inline-block;padding:14px 32px;color:{COLOR_WHITE};'
        f"font-family:{FONT_STACK};font-size:15px;font-weight:700;"
        f'text-decoration:none;border-radius:6px;">'
        f"{label}"
        f"</a>"
        f"</td>"
        f"</tr>"
        f"</table>"
    )


def render_info_box(content: str, *, bg_color: str = COLOR_HIGHLIGHT_BG) -> str:
    """Render a highlighted info box for displaying key details."""
    return (
        f'<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%"'
        f' style="margin:16px 0;">'
        f"<tr>"
        f'<td style="padding:16px 20px;background-color:{bg_color};border-radius:8px;'
        f"border:1px solid {COLOR_BORDER};font-family:{FONT_STACK};font-size:15px;"
        f'line-height:1.6;color:{COLOR_TEXT};">'
        f"{content}"
        f"</td>"
        f"</tr>"
        f"</table>"
    )


def render_code_block(code: str) -> str:
    """Render a large centered code/token display."""
    return (
        f'<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%"'
        f' style="margin:20px 0;">'
        f"<tr>"
        f'<td align="center" style="padding:20px;background-color:{COLOR_HIGHLIGHT_BG};'
        f"border-radius:8px;border:1px solid {COLOR_BORDER};"
        f"font-family:'Courier New',Courier,monospace;font-size:28px;"
        f'font-weight:700;color:{COLOR_PRIMARY};letter-spacing:3px;">'
        f"{code}"
        f"</td>"
        f"</tr>"
        f"</table>"
    )
