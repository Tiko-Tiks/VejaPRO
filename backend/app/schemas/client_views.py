"""Client UI V3 — view model schemas (backend-driven, LOCKED)."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

# Document types enum (7.8) — UI rodo label ir url, neinterpretuoja type
DOCUMENT_TYPES = (
    "PRELIM_QUOTE",
    "INVOICE_DEPOSIT",
    "CONTRACT",
    "SCHEDULE",
    "CERTIFICATE",
    "INVOICE_FINAL",
    "WARRANTY",
)


class ClientAction(BaseModel):
    """Single action (primary or secondary). action_key maps to POST /api/v1/client/actions/<action_key>."""

    action_key: str
    label: str
    href: Optional[str] = None
    method: Optional[str] = None
    payload: Optional[dict[str, Any]] = None


class ClientDocument(BaseModel):
    type: str  # from DOCUMENT_TYPES enum
    label: str
    url: Optional[str] = None
    expires_at: Optional[str] = None
    download_action: Optional[ClientAction] = None


class ActionRequiredItem(BaseModel):
    project_id: str
    title: str
    status: str
    status_hint: str
    next_step_text: str
    primary_action: Optional[ClientAction] = None
    secondary_action: Optional[ClientAction] = None


class ProjectCard(BaseModel):
    id: str
    title: str
    status: str
    status_hint: str
    summary: str
    documents: list[ClientDocument] = Field(default_factory=list)
    primary_action: Optional[ClientAction] = None


class UpsellCard(BaseModel):
    id: str
    title: str
    price_display: str
    benefit: str
    action_key: str


class FeatureFlags(BaseModel):
    stripe: bool = False
    vision_ai: bool = False
    subscriptions: bool = False


class ClientDashboardResponse(BaseModel):
    action_required: list[ActionRequiredItem] = Field(default_factory=list)
    projects: list[ProjectCard] = Field(default_factory=list)
    upsell_cards: list[UpsellCard] = Field(default_factory=list)
    feature_flags: FeatureFlags = Field(default_factory=FeatureFlags)


class TimelineStep(BaseModel):
    key: str
    label: str
    done: bool
    current: bool


class PaymentsSummary(BaseModel):
    deposit_state: str  # e.g. "PAID" / "PENDING"
    final_state: Optional[str] = None
    next_text: str


class AddonsAllowed(BaseModel):
    mode: str  # "attach" | "separate_request"
    reason: Optional[str] = None


class EstimateInfo(BaseModel):
    service: str
    service_label: str
    method: str
    method_label: str
    area_m2: float
    address: str
    phone: str
    total_eur: float
    preferred_slot: Optional[str] = None
    extras: Optional[str] = None
    submitted_at: str


class VisitInfo(BaseModel):
    visit_type: str  # "PRIMARY" | "SECONDARY"
    status: str  # "CONFIRMED" | "HELD" | "NONE"
    starts_at: Optional[str] = None
    label: Optional[str] = None


class ProjectViewResponse(BaseModel):
    status: str
    status_hint: str
    next_step_text: str
    primary_action: Optional[ClientAction] = None
    secondary_actions: list[ClientAction] = Field(default_factory=list)
    documents: list[ClientDocument] = Field(default_factory=list)
    timeline: list[TimelineStep] = Field(default_factory=list)
    payments_summary: Optional[PaymentsSummary] = None
    addons_allowed: AddonsAllowed = Field(default_factory=lambda: AddonsAllowed(mode="separate_request", reason=None))
    estimate_info: Optional[EstimateInfo] = None
    editable: bool = False
    visits: list[VisitInfo] = Field(default_factory=list)
    can_request_secondary_slot: bool = False
    preferred_secondary_slot: Optional[str] = None


# ─── Schedule slots ──────────────────────────────────────────────────────


class AvailableSlot(BaseModel):
    starts_at: str
    ends_at: str
    label: str


class AvailableSlotsResponse(BaseModel):
    slots: list[AvailableSlot] = Field(default_factory=list)


class SecondarySlotRequest(BaseModel):
    preferred_slot_start: str = Field(..., min_length=10, max_length=40)


class SecondarySlotResponse(BaseModel):
    message: str


# ─── Draft update ────────────────────────────────────────────────────────


class DraftUpdateRequest(BaseModel):
    phone: Optional[str] = None
    address: Optional[str] = None
    area_m2: Optional[float] = Field(None, gt=0, le=100000)
    service: Optional[str] = None
    method: Optional[str] = None
    user_notes: Optional[str] = None
    preferred_slot_start: Optional[str] = None


class DraftUpdateResponse(BaseModel):
    message: str
    total_eur: Optional[float] = None


# ─── Estimate (Client UI V3 → V2 pricing) ────────────────────────────────


class EstimateRulesResponse(BaseModel):
    rules_version: str
    services: dict[str, Any]
    addons: list[dict[str, Any]]
    transport: dict[str, float]
    disclaimer: str


class BaseRangeSchema(BaseModel):
    """V3: base inputs for price calculation (service, area, logistics)."""

    service: str
    method: str
    area_m2: float = Field(..., gt=0, le=100000)
    km_one_way: float = Field(0, ge=0, le=1000)


class EstimatePriceRequest(BaseModel):
    rules_version: str
    service: str
    method: str
    area_m2: float = Field(..., gt=0, le=100000)
    km_one_way: float = Field(0, ge=0, le=1000)
    mole_net: bool = False
    addons_selected: Optional[list[str]] = None


class EstimatePriceResponse(BaseModel):
    base_eur: float
    rate_eur_m2: float
    transport_eur: float
    mole_net_eur: float
    total_eur: float
    breakdown: list[dict[str, Any]] = Field(default_factory=list)
    rules_version: str


class EstimateSubmitRequest(BaseModel):
    rules_version: str
    service: str
    method: str
    area_m2: float = Field(..., gt=0, le=100000)
    km_one_way: float = Field(0, ge=0, le=1000)
    mole_net: bool = False
    addons_selected: Optional[list[str]] = None
    phone: str = Field(..., min_length=3, max_length=30)
    address: str = Field(..., min_length=3, max_length=300)
    slope_flag: bool = False
    photo_file_ids: list[str] = Field(default_factory=list, max_length=8)
    user_notes: Optional[str] = None
    preferred_slot_start: Optional[str] = None


class EstimateSubmitResponse(BaseModel):
    project_id: str
    message: str
    price_result: Optional[dict[str, Any]] = None


class AdminFinalQuoteRequest(BaseModel):
    service: str
    method: str
    actual_area_m2: float = Field(..., gt=0, le=100000)
    final_total_eur: float = Field(..., gt=0)
    notes: Optional[str] = None


# ─── Services (Client UI V3) ──────────────────────────────────────────────


class ServiceCatalogItem(BaseModel):
    id: str
    title: str
    price_display: str
    benefit: str
    fixed_price: bool = False
    questions: list[dict[str, Any]] = Field(default_factory=list, max_length=3)


class ServicesCatalogResponse(BaseModel):
    catalog_version: Optional[str] = None
    items: list[ServiceCatalogItem] = Field(default_factory=list)


class ServiceRequestRequest(BaseModel):
    service_id: str
    project_id: Optional[str] = None
    answers: dict[str, str] = Field(default_factory=dict)
    photo_file_ids: list[str] = Field(default_factory=list, max_length=8)


class ServiceRequestResponse(BaseModel):
    request_id: str
    message: str
    eta_text: Optional[str] = None


# ─── Client actions (plan 7.2) ─────────────────────────────────────────────


class ClientActionPayload(BaseModel):
    project_id: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
