from datetime import datetime, timezone
from fastapi import HTTPException

from app.schemas.project import ProjectStatus


ALLOWED_TRANSITIONS = {
    ProjectStatus.DRAFT: [ProjectStatus.PAID],
    ProjectStatus.PAID: [ProjectStatus.SCHEDULED],
    ProjectStatus.SCHEDULED: [ProjectStatus.PENDING_EXPERT],
    ProjectStatus.PENDING_EXPERT: [ProjectStatus.CERTIFIED],
    ProjectStatus.CERTIFIED: [ProjectStatus.ACTIVE],
    ProjectStatus.ACTIVE: [],
}


def validate_transition(current: ProjectStatus, new: ProjectStatus) -> None:
    if new not in ALLOWED_TRANSITIONS.get(current, []):
        raise HTTPException(400, f"Negalimas perejimas: {current} -> {new}")


def apply_transition(project, new_status: ProjectStatus) -> None:
    validate_transition(ProjectStatus(project.status), new_status)
    project.status = new_status.value
    project.status_changed_at = datetime.now(timezone.utc)
