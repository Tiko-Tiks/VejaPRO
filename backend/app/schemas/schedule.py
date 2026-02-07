from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class RescheduleReason(str, Enum):
    WEATHER = "WEATHER"
    TECHNICAL_ISSUE = "TECHNICAL_ISSUE"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"
    TIME_OVERFLOW = "TIME_OVERFLOW"
    OTHER = "OTHER"


class RescheduleScope(str, Enum):
    DAY = "DAY"


class RescheduleRules(BaseModel):
    preserve_locked_level: int = Field(default=1, ge=0, le=2)
    allow_replace_with_weather_resistant: bool = True


class SuggestedAction(BaseModel):
    action: Literal["CANCEL", "CREATE"]
    appointment_id: Optional[str] = None
    project_id: Optional[str] = None
    call_request_id: Optional[str] = None
    visit_type: Optional[str] = "PRIMARY"
    resource_id: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    weather_class: Optional[str] = None

    @model_validator(mode="after")
    def validate_by_action(self):
        if self.action == "CANCEL":
            if not self.appointment_id:
                raise ValueError("CANCEL action requires appointment_id")
            return self

        if not self.resource_id:
            raise ValueError("CREATE action requires resource_id")
        if not self.starts_at or not self.ends_at:
            raise ValueError("CREATE action requires starts_at and ends_at")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        if not (self.project_id or self.call_request_id):
            raise ValueError("CREATE action requires project_id or call_request_id")
        return self


class ReschedulePreviewRequest(BaseModel):
    route_date: date
    resource_id: str = Field(..., min_length=1)
    scope: RescheduleScope = RescheduleScope.DAY
    reason: RescheduleReason
    comment: str = ""
    rules: RescheduleRules = Field(default_factory=RescheduleRules)


class RescheduleSummary(BaseModel):
    cancel_count: int
    create_count: int
    total_travel_minutes: int = 0
    skipped_locked_count: int = 0


class ReschedulePreviewResponse(BaseModel):
    preview_id: str
    preview_hash: str
    preview_expires_at: datetime
    original_appointment_ids: List[str]
    suggested_actions: List[SuggestedAction]
    summary: RescheduleSummary


class RescheduleConfirmRequest(BaseModel):
    preview_id: str = Field(..., min_length=1)
    preview_hash: str = Field(..., min_length=1)
    reason: RescheduleReason
    comment: str = ""
    expected_versions: Dict[str, int] = Field(default_factory=dict)
    suggested_actions: Optional[List[SuggestedAction]] = None
    original_appointment_ids: Optional[List[str]] = None
    route_date: Optional[date] = None
    resource_id: Optional[str] = None


class RescheduleConfirmResponse(BaseModel):
    success: bool
    new_appointment_ids: List[str]
    notifications_enqueued: bool
