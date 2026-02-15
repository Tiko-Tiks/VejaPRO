"""
Supabase Dashboard Email Template Generators

Generates branded HTML templates using Supabase Go template variables
({{ .ConfirmationURL }}, {{ .SiteURL }}, etc.).

Output is meant to be pasted into Supabase Dashboard:
  Authentication > Email Templates > [template type]

Usage:
    from app.services.email_supabase_templates import generate_supabase_confirmation_template
    html = generate_supabase_confirmation_template()
    # Paste the resulting HTML into Supabase Dashboard
"""

from __future__ import annotations

from app.services.email_html_base import (
    render_branded_email,
    render_cta_button,
)

# Supabase uses Go html/template syntax: {{ .VariableName }}
# These are NOT Python f-string variables — they pass through as literal text.
CONFIRMATION_URL_VAR = "{{ .ConfirmationURL }}"
SITE_URL_VAR = "{{ .SiteURL }}"


def generate_supabase_confirmation_template(*, logo_url: str = "") -> str:
    """Generate branded HTML for Supabase email confirmation (signup).

    Uses Supabase Go template variable: {{ .ConfirmationURL }}

    Paste output into: Supabase Dashboard > Authentication > Email Templates > Confirm signup
    Subject: VejaPRO - Patvirtinkite savo paskyra
    """
    body_content = (
        '<p style="margin:0 0 16px 0;font-size:18px;font-weight:700;color:#1a1a1a;">'
        "Sveiki atvyke i VejaPRO!"
        "</p>"
        '<p style="margin:0 0 16px 0;font-size:15px;">'
        "Dekojame uz registracija! Paspauskite mygtuka zemiau, "
        "kad patvirtintumete savo el. pasto adresa:"
        "</p>"
        f"{render_cta_button(url=CONFIRMATION_URL_VAR, label='Patvirtinti el. pasta')}"
        '<p style="margin:16px 0 8px 0;font-size:13px;color:#5a5a5a;">'
        "Jei mygtukas neveikia, nukopijuokite si adresa i narsykle:"
        "</p>"
        '<p style="margin:0 0 16px 0;font-size:13px;color:#5a5a5a;word-break:break-all;">'
        f'<a href="{CONFIRMATION_URL_VAR}" style="color:#2d7a50;">'
        f"{CONFIRMATION_URL_VAR}"
        "</a>"
        "</p>"
        '<p style="margin:16px 0 0 0;font-size:12px;color:#5a5a5a;border-top:1px solid #e2ddd5;padding-top:12px;">'
        "Jei jus neregistravotes VejaPRO, tiesiog ignoruokite si laiska."
        "</p>"
    )

    return render_branded_email(
        title="Patvirtinkite savo paskyra",
        body_content=body_content,
        preheader="Patvirtinkite savo VejaPRO paskyra",
        logo_url=logo_url,
    )


def generate_supabase_reset_password_template(*, logo_url: str = "") -> str:
    """Generate branded HTML for Supabase password reset.

    Uses Supabase Go template variable: {{ .ConfirmationURL }}

    Paste output into: Supabase Dashboard > Authentication > Email Templates > Reset password
    Subject: VejaPRO - Slaptazodzio atstatymas
    """
    body_content = (
        '<p style="margin:0 0 16px 0;font-size:18px;font-weight:700;color:#1a1a1a;">'
        "Slaptazodzio atstatymas"
        "</p>"
        '<p style="margin:0 0 16px 0;font-size:15px;">'
        "Gavome jusu prasyma atstatyti slaptazodi. "
        "Paspauskite mygtuka zemiau, kad nustatytumete nauja slaptazodi:"
        "</p>"
        f"{render_cta_button(url=CONFIRMATION_URL_VAR, label='Atstatyti slaptazodi')}"
        '<p style="margin:16px 0 8px 0;font-size:13px;color:#5a5a5a;">'
        "Jei mygtukas neveikia, nukopijuokite si adresa i narsykle:"
        "</p>"
        '<p style="margin:0 0 16px 0;font-size:13px;color:#5a5a5a;word-break:break-all;">'
        f'<a href="{CONFIRMATION_URL_VAR}" style="color:#2d7a50;">'
        f"{CONFIRMATION_URL_VAR}"
        "</a>"
        "</p>"
        '<p style="margin:16px 0 0 0;font-size:12px;color:#5a5a5a;border-top:1px solid #e2ddd5;padding-top:12px;">'
        "Jei jus neprasysite slaptazodzio atstatymo, tiesiog ignoruokite si laiska. "
        "Jusu paskyra lieka saugi."
        "</p>"
    )

    return render_branded_email(
        title="Slaptazodzio atstatymas",
        body_content=body_content,
        preheader="Atstatykite savo VejaPRO slaptazodi",
        logo_url=logo_url,
    )


def generate_supabase_magic_link_template(*, logo_url: str = "") -> str:
    """Generate branded HTML for Supabase magic link login.

    Uses Supabase Go template variable: {{ .ConfirmationURL }}

    Paste output into: Supabase Dashboard > Authentication > Email Templates > Magic link
    Subject: VejaPRO - Prisijungimo nuoroda
    """
    body_content = (
        '<p style="margin:0 0 16px 0;font-size:18px;font-weight:700;color:#1a1a1a;">'
        "Prisijungimo nuoroda"
        "</p>"
        '<p style="margin:0 0 16px 0;font-size:15px;">'
        "Paspauskite mygtuka zemiau, kad prisijungtumete prie savo VejaPRO paskyros:"
        "</p>"
        f"{render_cta_button(url=CONFIRMATION_URL_VAR, label='Prisijungti')}"
        '<p style="margin:16px 0 8px 0;font-size:13px;color:#5a5a5a;">'
        "Jei mygtukas neveikia, nukopijuokite si adresa i narsykle:"
        "</p>"
        '<p style="margin:0 0 16px 0;font-size:13px;color:#5a5a5a;word-break:break-all;">'
        f'<a href="{CONFIRMATION_URL_VAR}" style="color:#2d7a50;">'
        f"{CONFIRMATION_URL_VAR}"
        "</a>"
        "</p>"
        '<p style="margin:16px 0 0 0;font-size:12px;color:#5a5a5a;border-top:1px solid #e2ddd5;padding-top:12px;">'
        "Si nuoroda galioja tik viena karta. "
        "Jei jus neprasysite prisijungimo, tiesiog ignoruokite si laiska."
        "</p>"
    )

    return render_branded_email(
        title="Prisijungimo nuoroda",
        body_content=body_content,
        preheader="Jusu VejaPRO prisijungimo nuoroda",
        logo_url=logo_url,
    )
