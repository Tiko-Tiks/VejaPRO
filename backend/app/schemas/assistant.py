from datetime import date, datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class CallRequestStatus(StrEnum):
    NEW = "NEW"
    CONTACTED = "CONTACTED"
    SCHEDULED = "SCHEDULED"
    CLOSED = "CLOSED"


class AppointmentStatus(StrEnum):
    CANCELLED = "CANCELLED"
    HELD = "HELD"
    CONFIRMED = "CONFIRMED"


class CallRequestCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    phone: str = Field(..., min_length=4, max_length=32)
    email: Optional[str] = None
    preferred_time: Optional[datetime] = None
    notes: str = ""


class CallRequestUpdate(BaseModel):
    status: Optional[CallRequestStatus] = None
    preferred_time: Optional[datetime] = None
    notes: Optional[str] = None


class CallRequestOut(BaseModel):
    id: str
    name: str
    phone: str
    email: Optional[str] = None
    preferred_time: Optional[datetime] = None
    notes: Optional[str] = None
    status: CallRequestStatus
    source: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CallRequestListResponse(BaseModel):
    items: list[CallRequestOut]
    next_cursor: Optional[str] = None
    has_more: bool


class AppointmentCreate(BaseModel):
    project_id: Optional[str] = None
    call_request_id: Optional[str] = None
    starts_at: datetime
    ends_at: datetime
    notes: str = ""
    # Schedule Engine planning axis: appointments are either HELD, CONFIRMED, or CANCELLED.
    status: AppointmentStatus = AppointmentStatus.CONFIRMED

    @model_validator(mode="after")
    def validate_links(self):
        if not self.project_id and not self.call_request_id:
            raise ValueError("project_id or call_request_id is required")
        return self


class AppointmentUpdate(BaseModel):
    status: Optional[AppointmentStatus] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    notes: Optional[str] = None


class AppointmentOut(BaseModel):
    id: str
    project_id: Optional[str] = None
    call_request_id: Optional[str] = None
    resource_id: Optional[str] = None
    visit_type: Optional[str] = None
    starts_at: datetime
    ends_at: datetime
    status: AppointmentStatus
    lock_level: Optional[int] = None
    locked_at: Optional[datetime] = None
    locked_by: Optional[str] = None
    lock_reason: Optional[str] = None
    hold_expires_at: Optional[datetime] = None
    weather_class: Optional[str] = None
    route_date: Optional[date] = None
    route_sequence: Optional[int] = None
    row_version: Optional[int] = None
    superseded_by_id: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    cancelled_by: Optional[str] = None
    cancel_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AppointmentListResponse(BaseModel):
    items: list[AppointmentOut]
    next_cursor: Optional[str] = None
    has_more: bool
