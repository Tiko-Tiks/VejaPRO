#!/usr/bin/env python3
"""
Generate branded HTML email templates for Supabase Dashboard.

Usage:
    python backend/scripts/generate_supabase_email_templates.py --type confirmation
    python backend/scripts/generate_supabase_email_templates.py --type reset_password
    python backend/scripts/generate_supabase_email_templates.py --type magic_link
    python backend/scripts/generate_supabase_email_templates.py --type all

    # Save to file:
    python backend/scripts/generate_supabase_email_templates.py --type confirmation --output confirmation.html

After generating, paste the HTML into:
    Supabase Dashboard > Authentication > Email Templates > [template type]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from project root with PYTHONPATH=backend
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.email_supabase_templates import (  # noqa: E402
    generate_supabase_confirmation_template,
    generate_supabase_magic_link_template,
    generate_supabase_reset_password_template,
)

GENERATORS = {
    "confirmation": {
        "fn": generate_supabase_confirmation_template,
        "subject": "VejaPRO - Patvirtinkite savo paskyra",
        "dashboard_path": "Authentication > Email Templates > Confirm signup",
    },
    "reset_password": {
        "fn": generate_supabase_reset_password_template,
        "subject": "VejaPRO - Slaptazodzio atstatymas",
        "dashboard_path": "Authentication > Email Templates > Reset password",
    },
    "magic_link": {
        "fn": generate_supabase_magic_link_template,
        "subject": "VejaPRO - Prisijungimo nuoroda",
        "dashboard_path": "Authentication > Email Templates > Magic link",
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Supabase email templates")
    parser.add_argument(
        "--type",
        choices=[*GENERATORS.keys(), "all"],
        required=True,
        help="Template type to generate",
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--logo-url",
        default="",
        help="Override logo URL (default: uses public_base_url from config)",
    )
    args = parser.parse_args()

    types_to_gen = list(GENERATORS.keys()) if args.type == "all" else [args.type]

    output_parts = []
    for tmpl_type in types_to_gen:
        gen = GENERATORS[tmpl_type]
        html = gen["fn"](logo_url=args.logo_url)

        if len(types_to_gen) > 1:
            output_parts.append(f"<!-- ═══ {tmpl_type.upper()} ═══ -->")
            output_parts.append(f"<!-- Subject: {gen['subject']} -->")
            output_parts.append(f"<!-- Paste into: {gen['dashboard_path']} -->")
            output_parts.append("")

        output_parts.append(html)

        if len(types_to_gen) > 1:
            output_parts.append("")
            output_parts.append("")

    result = "\n".join(output_parts)

    if args.output:
        Path(args.output).write_text(result, encoding="utf-8")
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(result)

    # Print instructions to stderr
    for tmpl_type in types_to_gen:
        gen = GENERATORS[tmpl_type]
        print(f"\n--- {tmpl_type} ---", file=sys.stderr)
        print(f"  Subject: {gen['subject']}", file=sys.stderr)
        print(f"  Paste into: {gen['dashboard_path']}", file=sys.stderr)


if __name__ == "__main__":
    main()
