from datetime import datetime
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


class FinanceEntryType(StrEnum):
    EXPENSE = "EXPENSE"
    TAX = "TAX"
    ADJUSTMENT = "ADJUSTMENT"


class FinanceCategory(StrEnum):
    FUEL = "FUEL"
    REPAIR = "REPAIR"
    MATERIALS = "MATERIALS"
    SUBCONTRACTOR = "SUBCONTRACTOR"
    TAXES = "TAXES"
    INSURANCE = "INSURANCE"
    TOOLS = "TOOLS"
    OTHER = "OTHER"


class FinancePaymentMethod(StrEnum):
    CASH = "CASH"
    BANK_TRANSFER = "BANK_TRANSFER"
    CARD = "CARD"
    OTHER = "OTHER"


class FinanceDocumentStatus(StrEnum):
    NEW = "NEW"
    EXTRACTED = "EXTRACTED"
    READY = "READY"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    POSTED = "POSTED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"


# --- Ledger ---


class LedgerEntryCreate(BaseModel):
    project_id: Optional[str] = None
    entry_type: FinanceEntryType
    category: FinanceCategory
    description: str = ""
    amount: float = Field(..., gt=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    payment_method: Optional[FinancePaymentMethod] = None
    document_id: Optional[str] = None
    occurred_at: Optional[datetime] = None


class LedgerEntryOut(BaseModel):
    id: str
    project_id: Optional[str] = None
    entry_type: FinanceEntryType
    category: str
    description: Optional[str] = None
    amount: float
    currency: str
    payment_method: Optional[str] = None
    document_id: Optional[str] = None
    reverses_entry_id: Optional[str] = None
    recorded_by: Optional[str] = None
    occurred_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class LedgerListResponse(BaseModel):
    items: list[LedgerEntryOut]
    next_cursor: Optional[str] = None
    has_more: bool


class LedgerReverseRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=512)


# --- Summary / Reports ---


class ProjectFinanceSummary(BaseModel):
    project_id: str
    total_income: float
    total_expenses: float
    net_expenses: float
    profit: float


class PeriodFinanceSummary(BaseModel):
    period_start: datetime
    period_end: datetime
    total_income: float
    total_expenses: float
    net_expenses: float
    profit: float
    project_count: int


# --- Documents ---


class FinanceDocumentOut(BaseModel):
    id: str
    file_url: str
    file_hash: Optional[str] = None
    original_filename: Optional[str] = None
    status: FinanceDocumentStatus
    uploaded_by: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class FinanceDocumentListResponse(BaseModel):
    items: list[FinanceDocumentOut]
    next_cursor: Optional[str] = None
    has_more: bool


class DocumentExtractionOut(BaseModel):
    id: str
    document_id: str
    extracted_json: dict[str, Any]
    confidence: Optional[float] = None
    model_version: Optional[str] = None
    created_at: Optional[datetime] = None


class DocumentPostRequest(BaseModel):
    project_id: Optional[str] = None
    entry_type: FinanceEntryType = FinanceEntryType.EXPENSE
    category: FinanceCategory = FinanceCategory.OTHER
    description: str = ""
    amount: float = Field(..., gt=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    payment_method: Optional[FinancePaymentMethod] = None
    occurred_at: Optional[datetime] = None


class BulkPostRequest(BaseModel):
    document_ids: list[str] = Field(..., min_length=1)


class BulkPostResponse(BaseModel):
    posted: int
    skipped: int
    errors: list[str]


# --- Vendor Rules ---


class VendorRuleCreate(BaseModel):
    vendor_pattern: str = Field(..., min_length=1, max_length=256)
    default_category: FinanceCategory
    default_entry_type: FinanceEntryType = FinanceEntryType.EXPENSE


class VendorRuleOut(BaseModel):
    id: str
    vendor_pattern: str
    default_category: str
    default_entry_type: str
    is_active: bool
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class VendorRuleListResponse(BaseModel):
    items: list[VendorRuleOut]


# --- Quick Payment & Transition ---


class QuickPaymentRequest(BaseModel):
    payment_type: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    payment_method: str = Field(default="CASH", min_length=1, max_length=32)
    provider_event_id: str = Field(..., min_length=1, max_length=128)
    received_at: Optional[datetime] = None
    collection_context: Optional[str] = Field(default=None, max_length=32)
    receipt_no: Optional[str] = Field(default=None, max_length=64)
    proof_url: Optional[str] = None
    notes: str = ""
    transition_to: Optional[str] = None


class QuickPaymentResponse(BaseModel):
    success: bool
    payment_id: str
    payment_type: str
    amount: float
    status_changed: bool
    new_status: Optional[str] = None
    email_queued: bool = False
