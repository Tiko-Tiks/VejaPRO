"""V2.2 Intake schemas — questionnaire, offer, public response."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class IntakeQuestionnaireUpdate(BaseModel):
    email: Optional[str] = None
    address: Optional[str] = None
    service_type: Optional[str] = None
    phone: Optional[str] = None
    whatsapp_consent: Optional[bool] = None
    notes: Optional[str] = None
    urgency: Optional[str] = None
    expected_row_version: Optional[int] = None


class IntakeStateResponse(BaseModel):
    call_request_id: str
    questionnaire: dict[str, Any] = Field(default_factory=dict)
    workflow: dict[str, Any] = Field(default_factory=dict)
    active_offer: dict[str, Any] = Field(default_factory=dict)
    offer_history: list[dict[str, Any]] = Field(default_factory=list)
    questionnaire_complete: bool = False


class PrepareOfferRequest(BaseModel):
    kind: str = "INSPECTION"
    expected_row_version: Optional[int] = None


class PrepareOfferResponse(BaseModel):
    call_request_id: str
    slot_start: Optional[str] = None
    slot_end: Optional[str] = None
    resource_id: Optional[str] = None
    kind: str = "INSPECTION"
    phase: Optional[str] = None


class SendOfferResponse(BaseModel):
    call_request_id: str
    appointment_id: str
    hold_expires_at: str
    attempt_no: int
    phase: str


class PublicOfferView(BaseModel):
    slot_start: Optional[str] = None
    slot_end: Optional[str] = None
    address: Optional[str] = None
    kind: str = "INSPECTION"
    status: str = "UNKNOWN"


class OfferResponseRequest(BaseModel):
    action: str = Field(..., pattern="^(accept|reject)$")
    suggest_text: Optional[str] = None


class OfferResponseResult(BaseModel):
    status: str
    message: str
    next_slot_start: Optional[str] = None
    next_slot_end: Optional[str] = None


class ActivationConfirmRequest(BaseModel):
    action: str = Field(default="confirm", pattern="^(confirm)$")


class ActivationConfirmResponse(BaseModel):
    project_id: str
    new_status: str
    message: str
