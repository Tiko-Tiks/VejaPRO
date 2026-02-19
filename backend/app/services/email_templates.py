from __future__ import annotations

from html import escape as html_escape
from urllib.parse import quote
from typing import Any

from app.services.email_html_base import (
    render_branded_email,
    render_code_block,
    render_cta_button,
    render_info_box,
)
from app.core.config import get_settings

MISSING_FIELD_QUESTIONS: dict[str, str] = {
    "phone": "telefono numeris, kad galetume su jumis susisiekti",
    "address": "paslaugos vietos adresas (gatve, miestas)",
    "service_type": "kokios paslaugos jums reikia (pvz. vejos pjovimas, aeracija, tresimas)",
    "area_m2": "apytikslis vejos plotas (kvadratiniais metrais)",
}


def build_missing_data_body(client_name: str, missing_fields: list[str]) -> str:
    name = client_name or "Kliente"
    questions = "\n".join(
        f"  - {MISSING_FIELD_QUESTIONS[field]}" for field in missing_fields if field in MISSING_FIELD_QUESTIONS
    )

    return (
        f"Sveiki, {name},\n"
        f"\n"
        f"Aciu uz jusu uzklausa!\n"
        f"\n"
        f"Kad galetume paruosti jums pasiulyma, mums dar truksta sios informacijos:\n"
        f"{questions}\n"
        f"\n"
        f"Prasome atsakyti i si laiska su trukstama informacija.\n"
        f"\n"
        f"Pagarbiai,\n"
        f"VejaPRO komanda"
    )


# ── HTML inner-content builders ──────────────────────────────


def _html_final_payment_confirmation(token: str, confirm_url: str) -> str:
    safe_token = html_escape(token)
    safe_confirm_url = html_escape(confirm_url)
    return (
        '<p style="margin:0 0 16px 0;font-size:15px;">Sveiki,</p>'
        '<p style="margin:0 0 16px 0;font-size:15px;">'
        "Naudokite si patvirtinimo koda, kad uzbaigtu galutini mokejima:"
        "</p>"
        f"{render_code_block(safe_token)}"
        '<p style="margin:0 0 16px 0;font-size:15px;">'
        "Taip pat galite paspausti nuorodą:"
        "</p>"
        f'{render_cta_button(url=safe_confirm_url, label="Patvirtinti mokėjimą", color="#2d7a50")}'
        '<p style="margin:16px 0 8px 0;font-size:13px;color:#5a5a5a;">'
        f'Jei mygtukas neveikia, naudokite šią nuorodą: <a href="{safe_confirm_url}">{safe_confirm_url}</a>'
        "</p>"
        '<p style="margin:0 0 8px 0;font-size:13px;color:#5a5a5a;">'
        "Jei jus neprasysite sio kodo, tiesiog ignoruokite si laiska."
        "</p>"
    )


def _html_appointment_rescheduled(scheduled_at: str) -> str:
    safe_time = html_escape(scheduled_at)
    return (
        '<p style="margin:0 0 16px 0;font-size:15px;">Sveiki,</p>'
        '<p style="margin:0 0 16px 0;font-size:15px;">'
        "Jusu vizito laikas buvo pakeistas. Naujas laikas:"
        "</p>"
        f"{render_info_box(f'&#128197; <strong>{safe_time}</strong>')}"
        '<p style="margin:0 0 8px 0;font-size:15px;">'
        "Jei turite klausimu, susisiekite su mumis."
        "</p>"
        '<p style="margin:16px 0 0 0;font-size:15px;">Pagarbiai,<br/>VejaPRO komanda</p>'
    )


def _html_offer_email(slot_start: str, address: str, confirm_url: str) -> str:
    safe_slot = html_escape(slot_start)
    safe_address = html_escape(address)
    accept_url = html_escape(f"{confirm_url}?action=accept")
    reject_url = html_escape(f"{confirm_url}?action=reject")
    return (
        '<p style="margin:0 0 16px 0;font-size:15px;">Sveiki,</p>'
        '<p style="margin:0 0 16px 0;font-size:15px;">'
        "Siulome jums apziuros laika:"
        "</p>"
        f"{render_info_box(f'&#128197; <strong>Data/laikas:</strong> {safe_slot}<br/>&#128205; <strong>Adresas:</strong> {safe_address}')}"
        '<p style="margin:0 0 8px 0;font-size:15px;text-align:center;">'
        "Pasirinkite viena is variantu:"
        "</p>"
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">'
        "<tr>"
        '<td align="center" style="padding:8px;">'
        f"{render_cta_button(url=accept_url, label='Patvirtinti', color='#2d7a50')}"
        "</td>"
        '<td align="center" style="padding:8px;">'
        f"{render_cta_button(url=reject_url, label='Atsisakyti', color='#c0392b')}"
        "</td>"
        "</tr>"
        "</table>"
        '<p style="margin:16px 0 0 0;font-size:15px;">Pagarbiai,<br/>VejaPRO komanda</p>'
    )


def _html_missing_data(client_name: str, missing_fields: list[str]) -> str:
    safe_name = html_escape(client_name or "Kliente")
    items = ""
    for field in missing_fields:
        if field in MISSING_FIELD_QUESTIONS:
            items += f'<li style="margin:4px 0;">{html_escape(MISSING_FIELD_QUESTIONS[field])}</li>'

    return (
        f'<p style="margin:0 0 16px 0;font-size:15px;">Sveiki, {safe_name},</p>'
        '<p style="margin:0 0 16px 0;font-size:15px;">'
        "Aciu uz jusu uzklausa!"
        "</p>"
        '<p style="margin:0 0 8px 0;font-size:15px;">'
        "Kad galetume paruosti jums pasiulyma, mums dar truksta sios informacijos:"
        "</p>"
        f'<ul style="margin:0 0 16px 0;padding-left:20px;font-size:15px;">{items}</ul>'
        '<p style="margin:0 0 16px 0;font-size:15px;">'
        "Prasome atsakyti i si laiska su trukstama informacija."
        "</p>"
        '<p style="margin:16px 0 0 0;font-size:15px;">Pagarbiai,<br/>VejaPRO komanda</p>'
    )


def _html_client_portal_access(client_name: str, portal_url: str) -> str:
    safe_name = html_escape(client_name)
    safe_url = html_escape(portal_url)
    return (
        f'<p style="margin:0 0 16px 0;font-size:15px;">Sveiki, {safe_name},</p>'
        '<p style="margin:0 0 16px 0;font-size:15px;">'
        "Jusu VejaPRO kliento portalas paruostas."
        "</p>"
        f"{render_cta_button(url=safe_url, label='Prisijungti prie portalo')}"
        '<p style="margin:16px 0 0px 0;font-size:13px;color:#5a5a5a;">'
        "Nuoroda galioja 7 dienas."
        "</p>"
        '<p style="margin:0 0 8px 0;font-size:13px;color:#5a5a5a;">'
        f"Jei mygtukas neveikia, nukopijuokite si adresa i narsykle:<br/>"
        f'<a href="{safe_url}" style="color:#2d7a50;word-break:break-all;">{safe_url}</a>'
        "</p>"
    )


# ── Main template builder ────────────────────────────────────


def build_email_payload(template_key: str, *, to: str, **context: Any) -> dict[str, Any]:
    if template_key == "FINAL_PAYMENT_CONFIRMATION":
        token = str(context.get("token") or "").strip()
        base_url = (get_settings().public_base_url or "https://vejapro.lt").rstrip("/")
        confirmation_url = str(context.get("confirmation_url") or "").strip() or (
            f"{base_url}/api/v1/public/confirm-payment/{quote(token)}"
        )
        if not token:
            raise ValueError("token is required for FINAL_PAYMENT_CONFIRMATION")
        return {
            "to": to,
            "subject": "VejaPRO - Patvirtinkite galutini mokejima",
            "body_text": (
                "Jusu patvirtinimo kodas: {token}\n"
                "Patvirtinti mokėjimą galite čia:\n"
                f"{confirmation_url}"
            ).format(token=token),
            "body_html": render_branded_email(
                title="Mokejimo patvirtinimas",
                body_content=_html_final_payment_confirmation(token, confirmation_url),
                preheader=f"Jusu patvirtinimo kodas: {token}",
            ),
        }

    if template_key == "APPOINTMENT_RESCHEDULED":
        scheduled_at = str(context.get("scheduled_at") or "").strip()
        if not scheduled_at:
            raise ValueError("scheduled_at is required for APPOINTMENT_RESCHEDULED")
        return {
            "to": to,
            "subject": "VejaPRO: vizito laikas pakeistas",
            "body_text": f"Jusu vizito laikas pakeistas. Naujas laikas: {scheduled_at}.",
            "body_html": render_branded_email(
                title="Vizito laikas pakeistas",
                body_content=_html_appointment_rescheduled(scheduled_at),
                preheader=f"Naujas vizito laikas: {scheduled_at}",
            ),
        }

    if template_key == "OFFER_EMAIL":
        slot_start = str(context.get("slot_start") or "").strip() or "?"
        address = str(context.get("address") or "").strip()
        confirm_url = str(context.get("confirm_url") or "").strip()
        if not confirm_url:
            raise ValueError("confirm_url is required for OFFER_EMAIL")
        return {
            "to": to,
            "subject": "VejaPRO: Apziuros pasiulymas",
            "body_text": (
                "Sveiki,\n\n"
                "Siulome apziuros laika:\n"
                f"  Data/laikas: {slot_start}\n"
                f"  Adresas: {address}\n\n"
                f"Patvirtinti: {confirm_url}?action=accept\n"
                f"Atsisakyti: {confirm_url}?action=reject\n\n"
                "Pagarbiai,\nVejaPRO komanda"
            ),
            "body_html": render_branded_email(
                title="Apziuros pasiulymas",
                body_content=_html_offer_email(slot_start, address, confirm_url),
                preheader=f"Apziuros pasiulymas: {slot_start}",
            ),
        }

    if template_key == "EMAIL_AUTO_REPLY_MISSING_DATA":
        missing_fields = context.get("missing_fields")
        if not isinstance(missing_fields, list) or not missing_fields:
            raise ValueError("missing_fields is required for EMAIL_AUTO_REPLY_MISSING_DATA")
        client_name = str(context.get("client_name") or "").strip()
        inbound_subject = str(context.get("inbound_subject") or "").strip() or "Jusu uzklausa"
        return {
            "to": to,
            "subject": f"Re: {inbound_subject}",
            "body_text": build_missing_data_body(client_name, missing_fields),
            "body_html": render_branded_email(
                title="Trukstama informacija",
                body_content=_html_missing_data(client_name, missing_fields),
                preheader="Mums reikia papildomos informacijos jusu pasiulymui",
            ),
        }

    if template_key == "CLIENT_PORTAL_ACCESS":
        portal_url = str(context.get("portal_url") or "").strip()
        client_name = str(context.get("client_name") or "").strip() or "Kliente"
        if not portal_url:
            raise ValueError("portal_url is required for CLIENT_PORTAL_ACCESS")
        return {
            "to": to,
            "subject": "VejaPRO - Jusu kliento portalas",
            "body_text": (
                f"Sveiki, {client_name},\n\n"
                f"Jusu VejaPRO kliento portalas paruostas.\n"
                f"Prisijunkite paspaudus nuoroda:\n\n"
                f"  {portal_url}\n\n"
                f"Nuoroda galioja 7 dienas.\n\n"
                f"Pagarbiai,\n"
                f"VejaPRO komanda"
            ),
            "body_html": render_branded_email(
                title="Kliento portalas",
                body_content=_html_client_portal_access(client_name, portal_url),
                preheader=f"Jusu VejaPRO kliento portalas paruostas, {html_escape(client_name)}",
            ),
        }

    raise ValueError(f"Unknown email template: {template_key}")
