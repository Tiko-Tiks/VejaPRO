from __future__ import annotations

from typing import Any

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


def build_email_payload(template_key: str, *, to: str, **context: Any) -> dict[str, Any]:
    if template_key == "FINAL_PAYMENT_CONFIRMATION":
        token = str(context.get("token") or "").strip()
        if not token:
            raise ValueError("token is required for FINAL_PAYMENT_CONFIRMATION")
        return {
            "to": to,
            "subject": "VejaPRO - Patvirtinkite galutini mokejima",
            "body_text": f"Jusu patvirtinimo kodas: {token}",
        }

    if template_key == "APPOINTMENT_RESCHEDULED":
        scheduled_at = str(context.get("scheduled_at") or "").strip()
        if not scheduled_at:
            raise ValueError("scheduled_at is required for APPOINTMENT_RESCHEDULED")
        return {
            "to": to,
            "subject": "VejaPRO: vizito laikas pakeistas",
            "body_text": f"Jusu vizito laikas pakeistas. Naujas laikas: {scheduled_at}.",
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
        }

    raise ValueError(f"Unknown email template: {template_key}")
