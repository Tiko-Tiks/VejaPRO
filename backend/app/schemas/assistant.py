from datetime import datetime
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field, model_validator


class CallRequestStatus(str, Enum):
    NEW = "NEW"
    CONTACTED = "CONTACTED"
    SCHEDULED = "SCHEDULED"
    CLOSED = "CLOSED"


class AppointmentStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
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
    items: List[CallRequestOut]
    next_cursor: Optional[str] = None
    has_more: bool


class AppointmentCreate(BaseModel):
    project_id: Optional[str] = None
    call_request_id: Optional[str] = None
    starts_at: datetime
    ends_at: datetime
    notes: str = ""
    status: AppointmentStatus = AppointmentStatus.SCHEDULED

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
    starts_at: datetime
    ends_at: datetime
    status: AppointmentStatus
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AppointmentListResponse(BaseModel):
    items: List[AppointmentOut]
    next_cursor: Optional[str] = None
    has_more: bool
