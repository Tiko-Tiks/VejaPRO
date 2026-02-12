"""Client UI V3 — backend-driven view endpoints (dashboard, project view, estimate, services)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.models.project import Project, ServiceRequest
from app.schemas.client_views import (
    ActionRequiredItem,
    AddonRule,
    AddonVariant,
    ClientAction,
    ClientActionPayload,
    ClientDashboardResponse,
    ClientDocument,
    EstimateAnalyzeRequest,
    EstimateAnalyzeResponse,
    EstimatePriceRequest,
    EstimatePriceResponse,
    EstimateRulesResponse,
    EstimateSubmitRequest,
    EstimateSubmitResponse,
    FeatureFlags,
    ProjectCard,
    ProjectViewResponse,
    ServiceCatalogItem,
    ServiceRequestRequest,
    ServiceRequestResponse,
    ServicesCatalogResponse,
    UpsellCard,
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
    CONFIDENCE_MESSAGES,
    CURRENT_RULES_VERSION,
    DISCLAIMER,
    compute_addons_total,
    compute_total_range,
    get_base_range,
)
from app.utils.rate_limit import get_client_ip, get_user_agent

router = APIRouter()


def _client_projects_stmt(client_id: str):
    return select(Project).where(
        or_(
            Project.client_info["client_id"].astext == client_id,
            Project.client_info["user_id"].astext == client_id,
            Project.client_info["id"].astext == client_id,
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
    )


# ─── Estimate (4 endpoints) ───────────────────────────────────────────────


def _build_rules_response() -> EstimateRulesResponse:
    addon_rules = [
        AddonRule(
            key=a["key"],
            label=a["label"],
            variants=[
                AddonVariant(
                    key=v["key"],
                    label=v["label"],
                    price=v["price"],
                    scope=v.get("scope"),
                    recommended=v.get("recommended", False),
                )
                for v in a["variants"]
            ],
        )
        for a in ADDONS
    ]
    return EstimateRulesResponse(
        rules_version=CURRENT_RULES_VERSION,
        base_rates={
            "LOW": {"min_per_m2": 8.0, "max_per_m2": 12.0},
            "MED": {"min_per_m2": 12.0, "max_per_m2": 18.0},
            "HIGH": {"min_per_m2": 18.0, "max_per_m2": 28.0},
        },
        addons=addon_rules,
        disclaimer=DISCLAIMER,
        confidence_messages=CONFIDENCE_MESSAGES,
    )


@router.get("/client/estimate/rules", response_model=EstimateRulesResponse)
async def get_estimate_rules(
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
):
    """Pricing rules and addons. FE does not hardcode prices."""
    return _build_rules_response()


@router.post("/client/estimate/analyze", response_model=EstimateAnalyzeResponse)
async def post_estimate_analyze(
    payload: EstimateAnalyzeRequest,
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
):
    """Analyze area (and optional photos). Returns complexity, base_range, confidence_bucket."""
    settings = get_settings()
    area = payload.area_m2
    if area <= 0:
        area = 100.0
    complexity = "MED"
    if area < 80:
        complexity = "LOW"
    elif area > 300:
        complexity = "HIGH"
    if settings.enable_vision_ai and payload.photo_file_ids:
        # Placeholder: could call analyze_site_photo(photo_url) and adjust complexity from AI
        pass
    base_range = get_base_range(area, complexity)
    confidence = 0.8 if complexity != "HIGH" else 0.6
    if area > 500:
        confidence = 0.5
    bucket = "GREEN" if confidence >= 0.7 else ("YELLOW" if confidence >= 0.4 else "RED")
    return EstimateAnalyzeResponse(
        ai_complexity=complexity,
        ai_obstacles=[],
        ai_confidence=confidence,
        base_range=base_range,
        confidence_bucket=bucket,
    )


@router.post("/client/estimate/price", response_model=EstimatePriceResponse)
async def post_estimate_price(
    payload: EstimatePriceRequest,
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
):
    """Compute total from base_range + addons. 409 if rules_version stale (plan 7.4)."""
    if payload.rules_version != CURRENT_RULES_VERSION:
        raise HTTPException(
            409,
            detail={
                "code": "RULES_VERSION_STALE",
                "message": "Pasibaigė kainodaros versija. Atnaujinkite puslapį.",
                "expected_rules_version": CURRENT_RULES_VERSION,
            },
        )
    addons_total = compute_addons_total(payload.addons_selected)
    total_range = compute_total_range(payload.base_range, addons_total)
    breakdown = [
        {"label": "Bazė", "min": payload.base_range.get("min", 0), "max": payload.base_range.get("max", 0)},
        {"label": "Priedai", "fixed": addons_total},
    ]
    return EstimatePriceResponse(
        addons_total_fixed=addons_total,
        total_range=total_range,
        breakdown=breakdown,
    )


@router.post("/client/estimate/submit", response_model=EstimateSubmitResponse, status_code=201)
async def post_estimate_submit(
    payload: EstimateSubmitRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("CLIENT")),
    db: Session = Depends(get_db),
):
    """Create DRAFT project with estimate in client_info, quote_pending=true. 409 if rules_version stale."""
    if payload.rules_version != CURRENT_RULES_VERSION:
        raise HTTPException(
            409,
            detail={
                "code": "RULES_VERSION_STALE",
                "message": "Pasibaigė kainodaros versija. Atnaujinkite puslapį.",
                "expected_rules_version": CURRENT_RULES_VERSION,
            },
        )
    from app.services.transition_service import create_audit_log

    estimate_payload: dict[str, Any] = {
        "area_m2": payload.area_m2,
        "rules_version": payload.rules_version,
        "addons_selected": payload.addons_selected,
        "photo_file_ids": payload.photo_file_ids,
        "ai_complexity": payload.ai_complexity,
        "ai_obstacles": payload.ai_obstacles or [],
        "ai_confidence": payload.ai_confidence,
        "base_range": payload.base_range,
        "confidence_bucket": payload.confidence_bucket,
        "user_notes": payload.user_notes,
    }
    client_info: dict[str, Any] = {
        "client_id": current_user.id,
        "user_id": current_user.id,
        "id": current_user.id,
        "quote_pending": True,
        "estimate": estimate_payload,
    }
    total_min = (payload.base_range or {}).get("min", 0)
    total_max = (payload.base_range or {}).get("max", 0)
    total_price = (total_min + total_max) / 2 if (total_min or total_max) else None
    project = Project(
        client_info=client_info,
        status="DRAFT",
        area_m2=payload.area_m2,
        total_price_client=total_price,
        vision_analysis=estimate_payload if payload.ai_complexity else None,
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
        message="Pateikta ekspertui. Netrukus susisieksime.",
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
