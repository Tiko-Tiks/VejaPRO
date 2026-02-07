from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, List

from pydantic import BaseModel, Field, model_validator


class ProjectStatus(str, Enum):
    DRAFT = "DRAFT"
    PAID = "PAID"
    SCHEDULED = "SCHEDULED"
    PENDING_EXPERT = "PENDING_EXPERT"
    CERTIFIED = "CERTIFIED"
    ACTIVE = "ACTIVE"


class PaymentType(str, Enum):
    DEPOSIT = "DEPOSIT"
    FINAL = "FINAL"


class EvidenceCategory(str, Enum):
    SITE_BEFORE = "SITE_BEFORE"
    WORK_IN_PROGRESS = "WORK_IN_PROGRESS"
    EXPERT_CERTIFICATION = "EXPERT_CERTIFICATION"


class ProjectCreate(BaseModel):
    client_info: Optional[Dict[str, Any]] = None
    area_m2: Optional[float] = None
    name: Optional[str] = None

    @model_validator(mode="after")
    def ensure_client_info(self):
        if self.client_info:
            return self
        if self.name:
            self.client_info = {"name": self.name}
            return self
        raise ValueError("client_info or name is required")


class ProjectOut(BaseModel):
    id: str
    client_info: Dict[str, Any]
    status: ProjectStatus
    area_m2: Optional[float] = None
    total_price_client: Optional[float] = None
    internal_cost: Optional[float] = None
    vision_analysis: Optional[Dict[str, Any]] = None
    has_robot: bool
    is_certified: bool
    marketing_consent: bool
    marketing_consent_at: Optional[datetime] = None
    status_changed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    assigned_contractor_id: Optional[str] = None
    assigned_expert_id: Optional[str] = None
    scheduled_for: Optional[datetime] = None


class AuditLogOut(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    action: str
    old_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None
    actor_type: str
    actor_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None


class AuditLogListResponse(BaseModel):
    items: List[AuditLogOut]
    next_cursor: Optional[str] = None
    has_more: bool


class EvidenceOut(BaseModel):
    id: str
    project_id: str
    file_url: str
    category: str
    uploaded_by: Optional[str] = None
    uploaded_at: Optional[datetime] = None
    show_on_web: bool
    is_featured: bool
    location_tag: Optional[str] = None


class ProjectDetail(BaseModel):
    project: ProjectOut
    audit_logs: List[AuditLogOut]
    evidences: List[EvidenceOut]


class TransitionRequest(BaseModel):
    project_id: Optional[str] = Field(default=None, min_length=1)
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None
    actor: Optional[str] = None
    new_status: ProjectStatus

    @model_validator(mode="after")
    def normalize(self):
        if not self.project_id:
            if self.entity_id:
                self.project_id = self.entity_id
            else:
                raise ValueError("project_id or entity_id is required")
        if self.entity_type and self.entity_type != "project":
            raise ValueError("entity_type must be 'project'")
        return self


class MarketingConsentRequest(BaseModel):
    consent: bool = True


class MarketingConsentOut(BaseModel):
    success: bool
    marketing_consent: bool
    marketing_consent_at: Optional[datetime] = None


class ApproveEvidenceRequest(BaseModel):
    location_tag: Optional[str] = None
    is_featured: Optional[bool] = None


class UploadEvidenceResponse(BaseModel):
    evidence_id: str
    file_url: str
    category: EvidenceCategory


class CertifyRequest(BaseModel):
    project_id: str = Field(..., min_length=1)
    checklist: Dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class CertifyResponse(BaseModel):
    success: bool
    project_status: ProjectStatus
    certificate_ready: bool


class GalleryItem(BaseModel):
    id: str
    project_id: str
    before_url: Optional[str] = None
    after_url: str
    location_tag: Optional[str] = None
    is_featured: bool
    uploaded_at: datetime


class GalleryResponse(BaseModel):
    items: List[GalleryItem]
    next_cursor: Optional[str] = None
    has_more: bool


class AdminProjectOut(BaseModel):
    id: str
    status: ProjectStatus
    scheduled_for: Optional[datetime] = None
    assigned_contractor_id: Optional[str] = None
    assigned_expert_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AdminProjectListResponse(BaseModel):
    items: List[AdminProjectOut]
    next_cursor: Optional[str] = None
    has_more: bool


class ClientProjectListResponse(BaseModel):
    items: List[ProjectOut]
    next_cursor: Optional[str] = None
    has_more: bool


class AssignRequest(BaseModel):
    user_id: str = Field(..., min_length=1)


class MarginCreateRequest(BaseModel):
    service_type: str = Field(..., min_length=1, max_length=64)
    margin_percent: float = Field(..., ge=0)


class MarginOut(BaseModel):
    id: str
    service_type: str
    margin_percent: float
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    is_active: bool


class MarginListResponse(BaseModel):
    items: List[MarginOut]


class PaymentLinkRequest(BaseModel):
    payment_type: PaymentType
    amount: float = Field(..., gt=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None
    description: Optional[str] = None


class PaymentLinkResponse(BaseModel):
    url: str
    session_id: str
    amount: float
    currency: str
    payment_type: PaymentType
    expires_at: Optional[int] = None


class ManualPaymentRequest(BaseModel):
    payment_type: PaymentType
    amount: float = Field(..., gt=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    payment_method: str = Field(..., min_length=1, max_length=32)
    provider_event_id: str = Field(..., min_length=1, max_length=128)
    receipt_no: Optional[str] = Field(default=None, max_length=64)
    received_at: Optional[datetime] = None
    collection_context: Optional[str] = Field(default=None, max_length=32)
    proof_url: Optional[str] = None
    notes: str = ""

    @model_validator(mode="after")
    def normalize(self):
        self.currency = (self.currency or "EUR").upper()
        self.payment_method = (self.payment_method or "").strip().upper()
        self.provider_event_id = (self.provider_event_id or "").strip()
        if self.receipt_no is not None:
            self.receipt_no = self.receipt_no.strip() or None
        if self.collection_context is not None:
            self.collection_context = self.collection_context.strip().upper() or None
        if self.proof_url is not None:
            self.proof_url = self.proof_url.strip() or None
        return self


class ManualPaymentResponse(BaseModel):
    success: bool
    idempotent: bool = False
    payment_id: str
    provider: str
    status: str
    payment_type: PaymentType
    amount: float
    currency: str
