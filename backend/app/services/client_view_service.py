"""Client UI V3 — server-side view model logic (next step, actions, documents, upsell)."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.models.project import Payment, Project
from app.schemas.client_views import (
    AddonsAllowed,
    ClientAction,
    ClientDocument,
    EstimateInfo,
    PaymentsSummary,
    TimelineStep,
    UpsellCard,
)
from app.services.estimate_rules import ADDONS, SERVICES
from app.services.transition_service import (
    is_client_confirmed,
    is_deposit_payment_recorded,
    is_final_payment_recorded,
)

STATUS_STEPS = ["DRAFT", "PAID", "SCHEDULED", "PENDING_EXPERT", "CERTIFIED", "ACTIVE"]
STATUS_LABELS = {
    "DRAFT": "Juodraštis",
    "PAID": "Avansas gautas",
    "SCHEDULED": "Suplanuota",
    "PENDING_EXPERT": "Laukiama eksperto",
    "CERTIFIED": "Sertifikuota",
    "ACTIVE": "Aktyvus",
}
STATUS_HINTS = {
    "DRAFT": "Laukiama pateikimo arba avanso.",
    "PAID": "Avansas gautas. Planuojami darbai.",
    "SCHEDULED": "Darbai suplanuoti.",
    "PENDING_EXPERT": "Laukiama eksperto patikros.",
    "CERTIFIED": "Sertifikuota. Laukiama patvirtinimo.",
    "ACTIVE": "Projektas aktyvus.",
}


def _project_client_id(project: Project) -> Optional[str]:
    if not isinstance(project.client_info, dict):
        return None
    cid = project.client_info.get("client_id") or project.client_info.get("user_id") or project.client_info.get("id")
    return str(cid) if cid else None


def _project_title(project: Project) -> str:
    if not isinstance(project.client_info, dict):
        return "Projektas"
    return (
        project.client_info.get("name")
        or project.client_info.get("client_name")
        or project.client_info.get("title")
        or "Projektas"
    )


def _quote_pending(project: Project) -> bool:
    """Estimate submitted, waiting (quote in client_info)."""
    if not isinstance(project.client_info, dict):
        return False
    return bool(project.client_info.get("quote_pending") or project.client_info.get("estimate"))


def _contract_signed(project: Project) -> bool:
    """Contract signed (stored in client_info until we have document signature record)."""
    if not isinstance(project.client_info, dict):
        return False
    return bool(project.client_info.get("contract_signed"))


def _deposit_due(project: Project, db: Session) -> bool:
    return not is_deposit_payment_recorded(db, str(project.id))


def _final_paid(project: Project, db: Session) -> bool:
    return is_final_payment_recorded(db, str(project.id))


def _confirmation_pending(project: Project, db: Session) -> bool:
    return _final_paid(project, db) and not is_client_confirmed(db, str(project.id))


def _final_due(project: Project, db: Session) -> bool:
    return not _final_paid(project, db)


def compute_next_step_and_actions(
    project: Project,
    db: Session,
) -> tuple[str, Optional[ClientAction], list[ClientAction]]:
    """
    CTA mapping (plan section 8). Returns (next_step_text, primary_action, secondary_actions).
    secondary_actions max 2.
    """
    status = project.status
    next_text = ""
    primary: Optional[ClientAction] = None
    secondary: list[ClientAction] = []

    if status == "DRAFT":
        if _quote_pending(project):
            next_text = "Peržiūrėkite pateiktą įvertinimą."
            primary = ClientAction(action_key="view_quote_status", label="Peržiūrėti įvertinimą")
        elif _deposit_due(project, db):
            next_text = "Apmokėkite avansą, kad projektas būtų patvirtintas."
            primary = ClientAction(action_key="pay_deposit", label="Apmokėti depozitą")
        else:
            next_text = "Laukiama patvirtinimo."
            primary = ClientAction(action_key="view_quote_status", label="Peržiūrėti")

    elif status == "PAID":
        if not _contract_signed(project):
            next_text = "Pasirašykite sutartį."
            primary = ClientAction(action_key="sign_contract", label="Pasirašyti sutartį")
        else:
            next_text = "Suplanuoti darbai. Galite peržiūrėti grafiką."
            primary = ClientAction(action_key="view_schedule", label="Peržiūrėti grafiką")

    elif status == "SCHEDULED":
        next_text = "Darbai suplanuoti. Laukiama vykdymo."
        primary = ClientAction(action_key="open_project", label="Peržiūrėti projektą")

    elif status == "PENDING_EXPERT":
        next_text = "Laukiama eksperto patikros."
        primary = ClientAction(action_key="open_project", label="Peržiūrėti projektą")

    elif status == "CERTIFIED":
        if _final_due(project, db):
            next_text = "Apmokėkite likutį."
            primary = ClientAction(action_key="pay_final", label="Apmokėti likutį")
        elif _confirmation_pending(project, db):
            next_text = "Patvirtinkite gavimą (el. paštu arba SMS)."
            primary = ClientAction(action_key="confirm_acceptance", label="Patvirtinti")
        else:
            next_text = "Laukiama patvirtinimo."
            primary = ClientAction(action_key="open_project", label="Peržiūrėti")

    elif status == "ACTIVE":
        next_text = "Projektas aktyvus. Galite užsakyti priežiūrą."
        primary = ClientAction(action_key="order_maintenance", label="Užsisakyti priežiūrą")

    else:
        next_text = STATUS_HINTS.get(status, "Peržiūrėkite projektą.")
        primary = ClientAction(action_key="open_project", label="Atidaryti projektą")

    secondary.append(ClientAction(action_key="open_project", label="Peržiūrėti"))
    secondary = secondary[:2]

    return next_text, primary, secondary


def get_documents_for_status(project: Project, base_url: str = "") -> list[ClientDocument]:
    """Documents allowed per status (plan 7.8). URLs are placeholders; signed URL in 10.3."""
    status = project.status
    docs: list[ClientDocument] = []
    if status in ("DRAFT", "PAID", "SCHEDULED", "PENDING_EXPERT", "CERTIFIED", "ACTIVE"):
        if status == "DRAFT":
            docs.append(
                ClientDocument(
                    type="PRELIM_QUOTE",
                    label="Preliminari sąmata",
                    url=f"{base_url}/api/v1/projects/{project.id}/quote",
                )
            )
        if status in ("PAID", "SCHEDULED", "PENDING_EXPERT", "CERTIFIED", "ACTIVE"):
            docs.append(
                ClientDocument(
                    type="INVOICE_DEPOSIT",
                    label="Avansinė sąskaita",
                    url=f"{base_url}/api/v1/projects/{project.id}/invoice-deposit",
                )
            )
            docs.append(
                ClientDocument(
                    type="CONTRACT", label="Sutartis", url=f"{base_url}/api/v1/projects/{project.id}/contract"
                )
            )
        if status in ("SCHEDULED", "PENDING_EXPERT", "CERTIFIED", "ACTIVE"):
            docs.append(
                ClientDocument(
                    type="SCHEDULE", label="Grafikas", url=f"{base_url}/api/v1/projects/{project.id}/schedule"
                )
            )
        if status in ("CERTIFIED", "ACTIVE"):
            docs.append(
                ClientDocument(
                    type="CERTIFICATE", label="Sertifikatas", url=f"{base_url}/api/v1/projects/{project.id}/certificate"
                )
            )
        if status == "ACTIVE":
            docs.append(
                ClientDocument(
                    type="INVOICE_FINAL",
                    label="Galutinė sąskaita",
                    url=f"{base_url}/api/v1/projects/{project.id}/invoice-final",
                )
            )
            docs.append(
                ClientDocument(
                    type="WARRANTY", label="Garantinis lapas", url=f"{base_url}/api/v1/projects/{project.id}/warranty"
                )
            )
    return docs


def build_timeline(project: Project) -> list[TimelineStep]:
    idx = next((i for i, s in enumerate(STATUS_STEPS) if s == project.status), 0)
    return [
        TimelineStep(
            key=step,
            label=STATUS_LABELS.get(step, step),
            done=i < idx,
            current=(i == idx),
        )
        for i, step in enumerate(STATUS_STEPS)
    ]


def _payment_total(db: Session, project_id: str, payment_type: str) -> float | None:
    """Sum of succeeded payments for a given type (DEPOSIT / FINAL)."""
    row = (
        db.query(sa_func.sum(Payment.amount))
        .filter(
            Payment.project_id == project_id,
            Payment.payment_type == payment_type,
            Payment.status == "SUCCEEDED",
        )
        .scalar()
    )
    return float(row) if row else None


def build_payments_summary(project: Project, db: Session) -> PaymentsSummary:
    deposit_ok = is_deposit_payment_recorded(db, str(project.id))
    final_ok = is_final_payment_recorded(db, str(project.id))
    confirmed = is_client_confirmed(db, str(project.id))
    if project.status == "ACTIVE":
        next_text = "Projektas aktyvus."
    elif project.status == "CERTIFIED":
        if not final_ok:
            next_text = "Apmokėkite likutį."
        elif not confirmed:
            next_text = "Patvirtinkite gavimą."
        else:
            next_text = "Laukiama aktyvavimo."
    elif deposit_ok:
        next_text = "Avansas gautas."
    else:
        next_text = "Apmokėkite avansą."

    pid = str(project.id)
    deposit_amt = _payment_total(db, pid, "DEPOSIT") if deposit_ok else None
    final_amt = _payment_total(db, pid, "FINAL") if final_ok else None

    return PaymentsSummary(
        deposit_state="PAID" if deposit_ok else "PENDING",
        deposit_amount_eur=deposit_amt,
        final_state="PAID" if final_ok else ("PENDING" if project.status == "CERTIFIED" else None),
        final_amount_eur=final_amt,
        next_text=next_text,
    )


def build_estimate_info(project: Project) -> EstimateInfo | None:
    """Extract EstimateInfo from project.client_info.estimate."""
    ci = dict(project.client_info or {})
    est = ci.get("estimate")
    if not est or not isinstance(est, dict):
        return None
    svc_key = est.get("service", "")
    method_key = est.get("method", "")
    svc_data = SERVICES.get(svc_key, {})
    method_data = (svc_data.get("methods") or {}).get(method_key, {})
    # Format preferred_slot_start to human-readable label
    raw_slot = est.get("preferred_slot_start")
    slot_label = None
    if raw_slot:
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(raw_slot.replace("Z", "+00:00"))
            slot_label = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, AttributeError):
            slot_label = str(raw_slot)

    # Convert addon keys to human-readable labels
    raw_addons = est.get("addons_selected") or []
    addon_labels = [ADDONS.get(k, {}).get("label", k) for k in raw_addons]

    return EstimateInfo(
        service=svc_key,
        service_label=svc_data.get("label", svc_key),
        method=method_key,
        method_label=method_data.get("label", method_key),
        area_m2=est.get("area_m2", 0),
        address=est.get("address", ""),
        phone=est.get("phone", ""),
        km_one_way=est.get("km_one_way"),
        addons_selected=addon_labels,
        total_eur=est.get("total_eur", 0),
        preferred_slot=slot_label,
        extras=est.get("user_notes"),
        submitted_at=est.get("submitted_at", ""),
    )


def addons_allowed_for_project(project: Project) -> AddonsAllowed:
    """Plan: project.status >= PAID -> separate_request."""
    if project.status in ("PAID", "SCHEDULED", "PENDING_EXPERT", "CERTIFIED", "ACTIVE"):
        return AddonsAllowed(mode="separate_request", reason="Papildomos paslaugos užsakomos atskirai.")
    return AddonsAllowed(mode="attach", reason=None)


def action_required_for_project(project: Project, db: Session) -> bool:
    """True if this project needs client action (for dashboard ordering)."""
    status = project.status
    if status == "DRAFT":
        return _deposit_due(project, db)
    if status == "PAID":
        return not _contract_signed(project)
    if status == "CERTIFIED":
        return _final_due(project, db) or _confirmation_pending(project, db)
    if status == "ACTIVE":
        return True
    return False


def get_upsell_cards(has_non_active: bool, has_active: bool) -> list[UpsellCard]:
    """Deterministic 3–6 cards. pre_active -> add-on; active -> retention."""
    cards: list[UpsellCard] = []
    if has_non_active:
        cards.extend(
            [
                UpsellCard(
                    id="watering",
                    title="Laistymo sistema",
                    price_display="nuo 299 €",
                    benefit="Sutaupo laiką.",
                    action_key="open_services_catalog",
                ),
                UpsellCard(
                    id="seed_premium",
                    title="Premium sėkla",
                    price_display="nuo 89 €",
                    benefit="Geresnė kokybė.",
                    action_key="open_services_catalog",
                ),
                UpsellCard(
                    id="starter_fertilizer",
                    title="Startinis tręšimas",
                    price_display="nuo 49 €",
                    benefit="Greitesnė pradžia.",
                    action_key="open_services_catalog",
                ),
                UpsellCard(
                    id="robot",
                    title="Vejos robotas",
                    price_display="Kaina po įvertinimo",
                    benefit="Vienose rankose.",
                    action_key="open_services_catalog",
                ),
            ]
        )
    if has_active:
        cards.extend(
            [
                UpsellCard(
                    id="maintenance_plan",
                    title="Priežiūros planas",
                    price_display="nuo 29 €/mėn",
                    benefit="Reguliarus priežiūra.",
                    action_key="open_services_catalog",
                ),
                UpsellCard(
                    id="fertilizer_plan",
                    title="Tręšimo planas",
                    price_display="Kaina po įvertinimo",
                    benefit="Sezoninis tręšimas.",
                    action_key="open_services_catalog",
                ),
                UpsellCard(
                    id="diagnostics",
                    title="Diagnostika (nedygsta / liga)",
                    price_display="Kaina po įvertinimo",
                    benefit="Eksperto įvertinimas.",
                    action_key="open_services_catalog",
                ),
                UpsellCard(
                    id="robot_service",
                    title="Roboto servisas",
                    price_display="nuo 59 €",
                    benefit="Techninė priežiūra.",
                    action_key="open_services_catalog",
                ),
            ]
        )
    if not cards:
        cards.append(
            UpsellCard(
                id="estimate",
                title="Įvertinti sklypą",
                price_display="Nemokamai",
                benefit="Gaukite preliminarų įvertinimą.",
                action_key="open_estimate",
            )
        )
    return cards[:6]
