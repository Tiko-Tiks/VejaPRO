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


# ─── Estimate (Client UI V3) ─────────────────────────────────────────────


class AddonVariant(BaseModel):
    key: str
    label: str
    price: float
    scope: Optional[str] = None
    recommended: bool = False


class AddonRule(BaseModel):
    key: str
    label: str
    variants: list[AddonVariant]


class EstimateRulesResponse(BaseModel):
    rules_version: str
    base_rates: dict[str, dict[str, float]]  # LOW/MED/HIGH -> min/max per m² or total
    addons: list[AddonRule]
    disclaimer: str
    confidence_messages: dict[str, str]  # GREEN/YELLOW/RED -> text


class EstimateAnalyzeRequest(BaseModel):
    area_m2: float = Field(..., gt=0, le=100000)
    photo_file_ids: list[str] = Field(default_factory=list, max_length=8)


class EstimateAnalyzeResponse(BaseModel):
    ai_complexity: str  # LOW | MED | HIGH
    ai_obstacles: list[str] = Field(default_factory=list)
    ai_confidence: float = Field(..., ge=0, le=1)
    base_range: dict[str, float]  # min, max
    confidence_bucket: str  # GREEN | YELLOW | RED


class EstimatePriceRequest(BaseModel):
    rules_version: str
    base_range: dict[str, float]
    addons_selected: list[dict[str, str]] = Field(default_factory=list)  # [{"key": "seed", "variant": "premium"}]


class EstimatePriceResponse(BaseModel):
    addons_total_fixed: float
    total_range: dict[str, float]
    breakdown: list[dict[str, Any]] = Field(default_factory=list)


class EstimateSubmitRequest(BaseModel):
    area_m2: float = Field(..., gt=0, le=100000)
    rules_version: str
    addons_selected: list[dict[str, str]] = Field(default_factory=list)
    photo_file_ids: list[str] = Field(default_factory=list, max_length=8)
    user_notes: Optional[str] = None
    ai_complexity: Optional[str] = None
    ai_obstacles: Optional[list[str]] = None
    ai_confidence: Optional[float] = None
    base_range: Optional[dict[str, float]] = None
    confidence_bucket: Optional[str] = None


class EstimateSubmitResponse(BaseModel):
    project_id: str
    message: str


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
