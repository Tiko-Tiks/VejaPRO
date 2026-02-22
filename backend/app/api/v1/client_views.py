"""Client UI V3 — backend-driven view endpoints (dashboard, project view, estimate, services)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.models.project import Appointment, Project, ServiceRequest
from app.schemas.client_views import (
    ActionRequiredItem,
    AvailableSlotsResponse,
    ClientAction,
    ClientActionPayload,
    ClientDashboardResponse,
    ClientDocument,
    DraftUpdateRequest,
    DraftUpdateResponse,
    EstimateInfo,
    EstimatePriceRequest,
    EstimatePriceResponse,
    EstimateRulesResponse,
    EstimateSubmitRequest,
    EstimateSubmitResponse,
    FeatureFlags,
    ProjectCard,
    ProjectViewResponse,
    SecondarySlotRequest,
    SecondarySlotResponse,
    ServiceCatalogItem,
    ServiceRequestRequest,
    ServiceRequestResponse,
    ServicesCatalogResponse,
    UpsellCard,
    VisitInfo,
)
from app.services.client_view_service import (
    STATUS_HINTS,
    _project_client_id,
    _project_title,
    action_required_for_project,
    addons_allowed_for_project,
    build_payments_summary,
    build_timeline,
    compute_next_step_and_actions,
    get_documents_for_status,
    get_upsell_cards,
)
from app.services.estimate_rules import (
    ADDONS,
    CURRENT_RULES_VERSION,
    SERVICES,
    compute_price,
    get_rules,
    get_valid_addon_keys,
)
from app.utils.rate_limit import get_client_ip, get_user_agent

router = APIRouter()


def _client_projects_stmt(client_id: str):
    return select(Project).where(
        or_(
            Project.client_info["client_id"].as_string() == client_id,
            Project.client_info["user_id"].as_string() == client_id,
            Project.client_info["id"].as_string() == client_id,
        )
    )


@router.get("/client/dashboard", response_model=ClientDashboardResponse)
async def get_client_dashboard(
    request: Request,
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
    db: Session = Depends(get_db),
):
    """Single view model for client dashboard. No PII in response (7.9)."""
    client_id = current_user.id
    base_url = str(request.base_url).rstrip("/")
    settings = get_settings()

    rows = (
        db.execute(_client_projects_stmt(client_id).order_by(desc(Project.updated_at), desc(Project.id)))
        .scalars()
        .all()
    )
    projects = [r for r in rows]

    action_required: list[ActionRequiredItem] = []
    project_cards: list[ProjectCard] = []
    need_action_ids = {p.id for p in projects if action_required_for_project(p, db)}

    for project in projects:
        next_text, primary, secondary = compute_next_step_and_actions(project, db)
        title = _project_title(project)
        status_hint = STATUS_HINTS.get(project.status, "Peržiūrėkite projektą.")
        docs = get_documents_for_status(project, base_url)
        if need_action_ids and project.id in need_action_ids:
            action_required.append(
                ActionRequiredItem(
                    project_id=str(project.id),
                    title=title,
                    status=project.status,
                    status_hint=status_hint,
                    next_step_text=next_text,
                    primary_action=primary,
                    secondary_action=secondary[0] if secondary else None,
                )
            )
        summary = f"{status_hint} {next_text}".strip() or "Peržiūrėkite projektą."
        default_primary = primary or ClientAction(action_key="open_project", label="Atidaryti projektą")
        project_cards.append(
            ProjectCard(
                id=str(project.id),
                title=title,
                status=project.status,
                status_hint=status_hint,
                summary=summary,
                documents=docs,
                primary_action=default_primary,
            )
        )

    has_non_active = any(p.status != "ACTIVE" for p in projects)
    has_active = any(p.status == "ACTIVE" for p in projects)
    upsell_cards: list[UpsellCard] = get_upsell_cards(has_non_active, has_active)

    feature_flags = FeatureFlags(
        stripe=settings.enable_stripe,
        vision_ai=settings.enable_vision_ai,
        subscriptions=False,
    )
    return ClientDashboardResponse(
        action_required=action_required,
        projects=project_cards,
        upsell_cards=upsell_cards,
        feature_flags=feature_flags,
    )


@router.get("/client/projects/{project_id}/view", response_model=ProjectViewResponse)
async def get_client_project_view(
    project_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
    db: Session = Depends(get_db),
):
    """Single view model for project detail. 404 when no access (plan 10.1)."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Nerasta arba nėra prieigos")
    cid = _project_client_id(project)
    if cid != current_user.id:
        raise HTTPException(404, "Nerasta arba nėra prieigos")

    base_url = str(request.base_url).rstrip("/")
    next_text, primary, secondary = compute_next_step_and_actions(project, db)
    documents: list[ClientDocument] = get_documents_for_status(project, base_url)
    timeline = build_timeline(project)
    payments_summary = build_payments_summary(project, db)
    addons_allowed = addons_allowed_for_project(project)

    estimate_info = _build_estimate_info(project)
    client_info = dict(project.client_info or {})
    editable = project.status == "DRAFT" and client_info.get("quote_pending") is True

    # Build visits info
    appt_rows = (
        db.execute(
            select(Appointment).where(
                Appointment.project_id == project.id,
                Appointment.status != "CANCELLED",
            )
        )
        .scalars()
        .all()
    )
    visits: list[VisitInfo] = []
    for appt in appt_rows:
        starts_str = appt.starts_at.isoformat() if appt.starts_at else None
        label = None
        if appt.starts_at:
            label = appt.starts_at.strftime("%Y-%m-%d %H:%M")
        visits.append(
            VisitInfo(
                visit_type=appt.visit_type or "PRIMARY",
                status=appt.status,
                starts_at=starts_str,
                label=label,
            )
        )

    can_request_secondary = False
    if project.status in ("PAID", "SCHEDULED", "PENDING_EXPERT", "CERTIFIED"):
        has_primary_confirmed = any(v.visit_type == "PRIMARY" and v.status == "CONFIRMED" for v in visits)
        has_secondary_confirmed = any(v.visit_type == "SECONDARY" and v.status == "CONFIRMED" for v in visits)
        if has_primary_confirmed and not has_secondary_confirmed:
            can_request_secondary = True

    return ProjectViewResponse(
        status=project.status,
        status_hint=STATUS_HINTS.get(project.status, "Peržiūrėkite projektą."),
        next_step_text=next_text,
        primary_action=primary,
        secondary_actions=secondary[:2],
        documents=documents,
        timeline=timeline,
        payments_summary=payments_summary,
        addons_allowed=addons_allowed,
        estimate_info=estimate_info,
        editable=editable,
        visits=visits,
        can_request_secondary_slot=can_request_secondary,
        preferred_secondary_slot=client_info.get("preferred_secondary_slot"),
    )


def _build_estimate_info(project: Project) -> EstimateInfo | None:
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


# ─── Secondary slot preference ───────────────────────────────────────────


@router.post(
    "/client/projects/{project_id}/preferred-secondary-slot",
    response_model=SecondarySlotResponse,
)
async def post_preferred_secondary_slot(
    project_id: str,
    payload: SecondarySlotRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
    db: Session = Depends(get_db),
):
    """Save client's preferred time for secondary visit."""
    from app.services.transition_service import create_audit_log

    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Nerasta arba nėra prieigos")
    cid = _project_client_id(project)
    if cid != current_user.id:
        raise HTTPException(404, "Nerasta arba nėra prieigos")

    if project.status not in ("PAID", "SCHEDULED", "PENDING_EXPERT", "CERTIFIED"):
        raise HTTPException(400, "Antrojo vizito pageidavimas negalimas esant šiam statusui.")

    # Verify PRIMARY appointment is CONFIRMED
    primary_confirmed = (
        db.execute(
            select(Appointment).where(
                Appointment.project_id == project.id,
                Appointment.visit_type == "PRIMARY",
                Appointment.status == "CONFIRMED",
            )
        )
        .scalars()
        .first()
    )
    if not primary_confirmed:
        raise HTTPException(400, "Pirmasis vizitas dar nepatvirtintas.")

    client_info = dict(project.client_info or {})
    client_info["preferred_secondary_slot"] = payload.preferred_slot_start
    project.client_info = client_info
    db.add(project)
    db.flush()

    create_audit_log(
        db,
        entity_type="project",
        entity_id=str(project.id),
        action="SECONDARY_SLOT_REQUESTED",
        old_value=None,
        new_value={"preferred_secondary_slot": payload.preferred_slot_start},
        actor_type="CLIENT",
        actor_id=current_user.id,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    db.commit()

    return SecondarySlotResponse(message="Pageidaujamas antrojo vizito laikas išsaugotas.")


# ─── Schedule slots ──────────────────────────────────────────────────────


@router.get("/client/schedule/available-slots", response_model=AvailableSlotsResponse)
async def get_available_slots(
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
    db: Session = Depends(get_db),
):
    """Return available appointment slots for the client to choose from."""
    settings = get_settings()
    if not settings.enable_schedule_engine:
        raise HTTPException(404, "Nerasta")

    from app.services.schedule_slots import find_available_slots, pick_resource_id

    resource_id = pick_resource_id(db)
    if not resource_id:
        return AvailableSlotsResponse(slots=[])

    raw_slots = find_available_slots(db, resource_id, duration_min=60, count=10)
    return AvailableSlotsResponse(
        slots=[{"starts_at": s["starts_at"], "ends_at": s["ends_at"], "label": s["label"]} for s in raw_slots]
    )


# ─── Draft update ────────────────────────────────────────────────────────


@router.put("/client/projects/{project_id}/draft", response_model=DraftUpdateResponse)
async def put_draft_update(
    project_id: str,
    payload: DraftUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
    db: Session = Depends(get_db),
):
    """Update DRAFT project while quote_pending=true."""
    from app.services.transition_service import create_audit_log

    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Nerasta arba nėra prieigos")
    cid = _project_client_id(project)
    if cid != current_user.id:
        raise HTTPException(404, "Nerasta arba nėra prieigos")

    client_info = dict(project.client_info or {})
    if project.status != "DRAFT" or not client_info.get("quote_pending"):
        raise HTTPException(400, "Redagavimas galimas tik DRAFT projekte su laukiamu pasiūlymu.")

    estimate = dict(client_info.get("estimate") or {})
    changed_fields: dict[str, Any] = {}
    recalc_needed = False

    if payload.phone is not None:
        estimate["phone"] = payload.phone
        client_info["phone"] = payload.phone
        changed_fields["phone"] = payload.phone
    if payload.address is not None:
        estimate["address"] = payload.address
        changed_fields["address"] = payload.address
    if payload.area_m2 is not None:
        estimate["area_m2"] = payload.area_m2
        changed_fields["area_m2"] = payload.area_m2
        recalc_needed = True
    if payload.service is not None:
        estimate["service"] = payload.service
        changed_fields["service"] = payload.service
        recalc_needed = True
    if payload.method is not None:
        estimate["method"] = payload.method
        changed_fields["method"] = payload.method
        recalc_needed = True
    if payload.user_notes is not None:
        estimate["user_notes"] = payload.user_notes
        changed_fields["user_notes"] = payload.user_notes
    if payload.preferred_slot_start is not None:
        estimate["preferred_slot_start"] = payload.preferred_slot_start
        changed_fields["preferred_slot_start"] = payload.preferred_slot_start

    new_total: float | None = None
    if recalc_needed:
        try:
            price_result = compute_price(
                service=estimate.get("service", ""),
                method=estimate.get("method", ""),
                area_m2=estimate.get("area_m2", 0),
                km_one_way=estimate.get("km_one_way", 0),
                mole_net=estimate.get("mole_net", False),
            )
            estimate["total_eur"] = price_result["total_eur"]
            estimate["rate_eur_m2"] = price_result["rate_eur_m2"]
            estimate["transport_eur"] = price_result["transport_eur"]
            estimate["mole_net_eur"] = price_result["mole_net_eur"]
            new_total = price_result["total_eur"]
            project.area_m2 = estimate.get("area_m2", project.area_m2)
            project.total_price_client = new_total
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from None

    client_info["estimate"] = estimate
    project.client_info = client_info
    db.add(project)
    db.flush()

    create_audit_log(
        db,
        entity_type="project",
        entity_id=str(project.id),
        action="DRAFT_UPDATED",
        old_value=None,
        new_value=changed_fields,
        actor_type="CLIENT",
        actor_id=current_user.id,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    db.commit()

    return DraftUpdateResponse(
        message="Duomenys atnaujinti.",
        total_eur=new_total,
    )


# ─── Estimate (3 endpoints, V2 pricing) ──────────────────────────────────


def _normalise_addons_selected(
    addons_selected: Optional[list[str]],
    mole_net: bool,
) -> list[str]:
    """V3: addons_selected wins; else legacy mole_net → ['mole_net'] or []."""
    if addons_selected is not None and len(addons_selected) > 0:
        return sorted(addons_selected)
    return ["mole_net"] if mole_net else []


@router.get("/client/estimate/rules", response_model=EstimateRulesResponse)
async def get_estimate_rules(
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
):
    """Pricing rules v2. FE does not hardcode prices."""
    rules = get_rules()
    return EstimateRulesResponse(**rules)


@router.post("/client/estimate/price", response_model=EstimatePriceResponse)
async def post_estimate_price(
    payload: EstimatePriceRequest,
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
):
    """Compute total from service+method+area+transport+addons. 409 if rules_version stale."""
    if payload.rules_version != CURRENT_RULES_VERSION:
        raise HTTPException(
            409,
            detail={
                "code": "RULES_VERSION_STALE",
                "message": "Kainos taisykles pasikete. Atnaujinkite puslapi.",
                "expected_rules_version": CURRENT_RULES_VERSION,
            },
        )
    canonical_addons = _normalise_addons_selected(payload.addons_selected, payload.mole_net)
    valid_keys = set(get_valid_addon_keys())
    for key in canonical_addons:
        if key not in valid_keys:
            raise HTTPException(
                400,
                detail={"code": "UNKNOWN_ADDON", "message": f"Nezinomas priedas: {key!r}"},
            )
    mole_net = "mole_net" in canonical_addons
    try:
        result = compute_price(
            service=payload.service,
            method=payload.method,
            area_m2=payload.area_m2,
            km_one_way=payload.km_one_way,
            mole_net=mole_net,
        )
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from None
    return EstimatePriceResponse(**result)


@router.post("/client/estimate/submit", response_model=EstimateSubmitResponse, status_code=201)
async def post_estimate_submit(
    payload: EstimateSubmitRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
    db: Session = Depends(get_db),
):
    """Create DRAFT project with estimate in client_info, quote_pending=true. 409 if rules_version stale or duplicate."""
    if payload.rules_version != CURRENT_RULES_VERSION:
        raise HTTPException(
            409,
            detail={
                "code": "RULES_VERSION_STALE",
                "message": "Kainos taisykles pasikete. Atnaujinkite puslapi.",
                "expected_rules_version": CURRENT_RULES_VERSION,
            },
        )
    from datetime import datetime, timezone

    from app.services.transition_service import create_audit_log

    canonical_addons = _normalise_addons_selected(payload.addons_selected, payload.mole_net)
    valid_keys = set(get_valid_addon_keys())
    for key in canonical_addons:
        if key not in valid_keys:
            raise HTTPException(
                400,
                detail={"code": "UNKNOWN_ADDON", "message": f"Nezinomas priedas: {key!r}"},
            )
    mole_net = "mole_net" in canonical_addons
    try:
        price_result = compute_price(
            service=payload.service,
            method=payload.method,
            area_m2=payload.area_m2,
            km_one_way=payload.km_one_way,
            mole_net=mole_net,
        )
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from None

    # Block duplicate submissions — one active project per client
    from sqlalchemy import String, cast

    existing = (
        db.execute(select(Project).where(cast(Project.client_info, String).like(f'%"{current_user.id}"%')))
        .scalars()
        .first()
    )
    if existing:
        raise HTTPException(
            409,
            detail={
                "code": "DUPLICATE_ESTIMATE",
                "message": "Jūs jau turite pateiktą užklausą.",
                "project_id": str(existing.id),
            },
        )

    estimate_data: dict[str, Any] = {
        "service": payload.service,
        "method": payload.method,
        "area_m2": payload.area_m2,
        "km_one_way": payload.km_one_way,
        "mole_net": mole_net,
        "addons_selected": canonical_addons,
        "slope_flag": payload.slope_flag,
        "phone": payload.phone,
        "email": current_user.email,
        "address": payload.address,
        "total_eur": price_result["total_eur"],
        "rate_eur_m2": price_result["rate_eur_m2"],
        "transport_eur": price_result["transport_eur"],
        "mole_net_eur": price_result["mole_net_eur"],
        "rules_version": payload.rules_version,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "price_result": price_result,
    }
    if payload.preferred_slot_start:
        estimate_data["preferred_slot_start"] = payload.preferred_slot_start
    if payload.user_notes:
        estimate_data["user_notes"] = payload.user_notes

    client_info: dict[str, Any] = {
        "client_id": current_user.id,
        "user_id": current_user.id,
        "id": current_user.id,
        "phone": payload.phone,
        "email": current_user.email,
        "quote_pending": True,
        "estimate": estimate_data,
    }

    project = Project(
        client_info=client_info,
        status="DRAFT",
        area_m2=payload.area_m2,
        total_price_client=price_result["total_eur"],
    )
    db.add(project)
    db.flush()
    create_audit_log(
        db,
        entity_type="project",
        entity_id=str(project.id),
        action="ESTIMATE_SUBMITTED",
        old_value=None,
        new_value={"status": "DRAFT", "quote_pending": True},
        actor_type="CLIENT",
        actor_id=current_user.id,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    db.commit()
    db.refresh(project)
    return EstimateSubmitResponse(
        project_id=str(project.id),
        message="Uzklausa pateikta. Netrukus susisieksime.",
        price_result=price_result,
    )


# ─── Services catalog (deterministic, plan 7.6) ─────────────────────────────

SERVICE_CATALOG_VERSION = "v1"
SERVICE_CATALOG_PRE_ACTIVE = [
    ServiceCatalogItem(
        id="watering",
        title="Laistymo sistema",
        price_display="nuo 299 €",
        benefit="Sutaupo laiką.",
        fixed_price=False,
        questions=[],
    ),
    ServiceCatalogItem(
        id="seed_premium",
        title="Premium sėkla",
        price_display="nuo 89 €",
        benefit="Geresnė kokybė.",
        fixed_price=True,
        questions=[],
    ),
    ServiceCatalogItem(
        id="starter_fertilizer",
        title="Startinis tręšimas",
        price_display="nuo 49 €",
        benefit="Greitesnė pradžia.",
        fixed_price=True,
        questions=[],
    ),
    ServiceCatalogItem(
        id="robot",
        title="Vejos robotas",
        price_display="Kaina po įvertinimo",
        benefit="Vienose rankose.",
        fixed_price=False,
        questions=[{"key": "area", "label": "Plotas (m²)"}],
    ),
]
SERVICE_CATALOG_ACTIVE = [
    ServiceCatalogItem(
        id="maintenance_plan",
        title="Priežiūros planas",
        price_display="nuo 29 €/mėn",
        benefit="Reguliarus priežiūra.",
        fixed_price=False,
        questions=[],
    ),
    ServiceCatalogItem(
        id="fertilizer_plan",
        title="Tręšimo planas",
        price_display="Kaina po įvertinimo",
        benefit="Sezoninis tręšimas.",
        fixed_price=False,
        questions=[],
    ),
    ServiceCatalogItem(
        id="diagnostics",
        title="Diagnostika (nedygsta / liga)",
        price_display="Kaina po įvertinimo",
        benefit="Eksperto įvertinimas.",
        fixed_price=False,
        questions=[{"key": "description", "label": "Aprašymas"}],
    ),
    ServiceCatalogItem(
        id="robot_service",
        title="Roboto servisas",
        price_display="nuo 59 €",
        benefit="Techninė priežiūra.",
        fixed_price=False,
        questions=[],
    ),
]


@router.get("/client/services/catalog", response_model=ServicesCatalogResponse)
async def get_services_catalog(
    context: Optional[str] = None,
    project_id: Optional[str] = None,
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
    db: Session = Depends(get_db),
):
    """Deterministic 3–6 cards by context (pre_active | active). catalog_version for refetch (plan 7.6)."""
    items = []
    if context == "active":
        items = list(SERVICE_CATALOG_ACTIVE[:4])
    elif context == "pre_active":
        items = list(SERVICE_CATALOG_PRE_ACTIVE[:4])
    else:
        items = list(SERVICE_CATALOG_PRE_ACTIVE[:2]) + list(SERVICE_CATALOG_ACTIVE[:2])
    return ServicesCatalogResponse(catalog_version=SERVICE_CATALOG_VERSION, items=items[:6])


@router.post("/client/services/request", response_model=ServiceRequestResponse, status_code=201)
async def post_services_request(
    payload: ServiceRequestRequest,
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
    db: Session = Depends(get_db),
):
    """Create service_requests row. PAID+ project = always separate request (plan 2.4)."""
    project_id = None
    if payload.project_id:
        proj = db.get(Project, payload.project_id)
        if proj and _project_client_id(proj) == current_user.id:
            project_id = proj.id
    req = ServiceRequest(
        client_user_id=current_user.id,
        project_id=project_id,
        service_slug=payload.service_id,
        status="NEW",
        payload={"answers": payload.answers, "photo_file_ids": payload.photo_file_ids},
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return ServiceRequestResponse(
        request_id=str(req.id),
        message="Užklausa gauta. Susisieksime per 1–2 d.d.",
        eta_text="Kaina po įvertinimo per 1–2 d.d.",
    )


# ─── Client action endpoints (plan 7.2; UI never calls transition-status) ──


@router.post("/client/actions/pay-deposit")
async def client_action_pay_deposit(
    body: ClientActionPayload,
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
    db: Session = Depends(get_db),
):
    """Start deposit payment flow. Returns URL or instructions. Backend performs transition when payment recorded."""
    if not body.project_id:
        raise HTTPException(404, "Nerasta arba nėra prieigos")
    project = db.get(Project, body.project_id)
    if not project or _project_client_id(project) != current_user.id:
        raise HTTPException(404, "Nerasta arba nėra prieigos")
    if project.status != "DRAFT":
        raise HTTPException(400, "Avansas galimas tik DRAFT projekte.")
    return {
        "action": "message",
        "message": "Susisiekite su mumis dėl avanso mokėjimo arba mokėkite nuoroda, kurią atsiuntėme.",
        "contact": True,
    }


@router.post("/client/actions/sign-contract")
async def client_action_sign_contract(
    body: ClientActionPayload,
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
    db: Session = Depends(get_db),
):
    """Return contract document URL for signing."""
    if not body.project_id:
        raise HTTPException(404, "Nerasta arba nėra prieigos")
    project = db.get(Project, body.project_id)
    if not project or _project_client_id(project) != current_user.id:
        raise HTTPException(404, "Nerasta arba nėra prieigos")
    if project.status != "PAID":
        raise HTTPException(400, "Sutartis galima tik PAID projekte.")
    return {"action": "open", "url": f"/api/v1/projects/{project.id}/contract", "label": "Atidaryti sutartį"}


@router.post("/client/actions/pay-final")
async def client_action_pay_final(
    body: ClientActionPayload,
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
    db: Session = Depends(get_db),
):
    """Start final payment flow."""
    if not body.project_id:
        raise HTTPException(404, "Nerasta arba nėra prieigos")
    project = db.get(Project, body.project_id)
    if not project or _project_client_id(project) != current_user.id:
        raise HTTPException(404, "Nerasta arba nėra prieigos")
    if project.status != "CERTIFIED":
        raise HTTPException(400, "Likutis mokamas CERTIFIED projekte.")
    return {
        "action": "message",
        "message": "Susisiekite su mumis dėl likučio mokėjimo arba naudokite atsiųstą nuorodą.",
        "contact": True,
    }


@router.post("/client/actions/confirm-acceptance")
async def client_action_confirm_acceptance(
    body: ClientActionPayload,
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
    db: Session = Depends(get_db),
):
    """Trigger or return confirm link (email)."""
    if not body.project_id:
        raise HTTPException(404, "Nerasta arba nėra prieigos")
    project = db.get(Project, body.project_id)
    if not project or _project_client_id(project) != current_user.id:
        raise HTTPException(404, "Nerasta arba nėra prieigos")
    if project.status != "CERTIFIED":
        raise HTTPException(400, "Patvirtinimas galimas tik CERTIFIED projekte.")
    return {"action": "message", "message": "Patvirtinimo nuoroda išsiųsta el. paštu. Patikrinkite paštą."}


@router.post("/client/actions/order-service")
async def client_action_order_service(
    body: ClientActionPayload,
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
    db: Session = Depends(get_db),
):
    """Navigate to services catalog (optionally with project preselected)."""
    path = "#/services"
    if body.project_id:
        path = f"#/services?project_id={body.project_id}"
    return {"action": "navigate", "path": path, "message": "Papildomos paslaugos"}
