from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, or_, select
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.core.feature_flags import ensure_admin_ops_v1_enabled
from app.models.project import (
    Appointment,
    AuditLog,
    CallRequest,
    Evidence,
    FinanceLedgerEntry,
    Payment,
    Project,
    ProjectScheduling,
)
from app.schemas.client_views import AdminFinalQuoteRequest
from app.services.admin_read_models import (
    build_customer_profile,
    build_projects_view,
    derive_client_key,
    mask_email,
    mask_phone,
)
from app.services.client_view_service import (
    build_estimate_info,
    build_payments_summary,
    get_documents_for_status,
)
from app.services.transition_service import create_audit_log

router = APIRouter()
SYSTEM_ENTITY_ID = "00000000-0000-0000-0000-000000000000"


def _dialect_name(db: Session) -> str:
    dialect = getattr(getattr(db, "bind", None), "dialect", None)
    return (getattr(dialect, "name", "") or "").lower()


def _as_db_dt(db: Session, dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)
    if _dialect_name(db) == "sqlite":
        return dt_utc.replace(tzinfo=None)
    return dt_utc


def _iso_utc(dt: datetime | None) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _display_name(client_info: dict[str, Any] | None) -> str:
    if not isinstance(client_info, dict):
        return "Klientas"
    return str(client_info.get("name") or "").strip() or str(client_info.get("client_name") or "").strip() or "Klientas"


class DayPlanSummary(BaseModel):
    date: str
    total_minutes: int
    jobs_count: int


class DayPlanLinks(BaseModel):
    project: str
    client: str


class DayPlanItem(BaseModel):
    project_id: str | None = None
    client_key: str | None = None
    start: str | None = None
    end: str | None = None
    duration_min: int = 0
    title: str
    status: str
    budget: float | None = None
    links: DayPlanLinks


class DayPlanResponse(BaseModel):
    summary: DayPlanSummary
    items: list[DayPlanItem]


@router.get("/admin/ops/day/{for_date}/plan", response_model=DayPlanResponse)
def get_ops_day_plan(
    for_date: date,
    limit: int = Query(50, ge=1, le=50),
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    ensure_admin_ops_v1_enabled()

    day_start = datetime.combine(for_date, time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    start_db = _as_db_dt(db, day_start)
    end_db = _as_db_dt(db, day_end)

    rows = db.execute(
        select(Appointment, Project, ProjectScheduling)
        .outerjoin(Project, Project.id == Appointment.project_id)
        .outerjoin(ProjectScheduling, ProjectScheduling.project_id == Appointment.project_id)
        .where(Appointment.starts_at >= start_db)
        .where(Appointment.starts_at < end_db)
        .where(Appointment.status.in_(["HELD", "CONFIRMED"]))
        .order_by(Appointment.starts_at.asc(), Appointment.id.asc())
        .limit(limit)
    ).all()

    items: list[DayPlanItem] = []
    total_minutes = 0
    day_iso = for_date.isoformat()

    for appt, project, scheduling in rows:
        start = _iso_utc(appt.starts_at)
        end = _iso_utc(appt.ends_at)
        actual_duration_min = 0
        if appt.starts_at and appt.ends_at:
            actual_duration_min = max(0, int((appt.ends_at - appt.starts_at).total_seconds() // 60))

        planned_duration_min = int(scheduling.estimated_duration_min) if scheduling else 0
        duration_min = planned_duration_min or actual_duration_min
        total_minutes += duration_min

        client_key: str | None = None
        title = "Darbas"
        status = appt.status
        budget: float | None = None
        project_link = "/admin/calendar"
        client_link = "/admin/customers"

        if project is not None:
            client_key, _ = derive_client_key(project.client_info if isinstance(project.client_info, dict) else None)
            if client_key == "unknown":
                client_key = None
            title = _display_name(project.client_info if isinstance(project.client_info, dict) else None)
            status = project.status or status
            budget = float(project.total_price_client) if project.total_price_client is not None else None
            project_link = f"/admin/project/{project.id}?day={day_iso}"
            if client_key:
                client_link = f"/admin/client/{client_key}"

        items.append(
            DayPlanItem(
                project_id=str(project.id) if project else None,
                client_key=client_key,
                start=start,
                end=end,
                duration_min=duration_min,
                title=title,
                status=status,
                budget=budget,
                links=DayPlanLinks(project=project_link, client=client_link),
            )
        )

    return DayPlanResponse(
        summary=DayPlanSummary(
            date=day_iso,
            total_minutes=total_minutes,
            jobs_count=len(items),
        ),
        items=items,
    )


class InboxTaskOut(BaseModel):
    task_id: str
    entity_type: str
    entity_id: str
    client_key: str | None = None
    task_type: str
    title: str
    reason: str
    action_key: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=3, ge=1, le=3)
    urgency: str = Field(default="low")
    updated_at: str | None = None


class InboxResponse(BaseModel):
    items: list[InboxTaskOut]
    generated_at: str
    limit: int


def _task_priority(urgency: str) -> int:
    if urgency == "high":
        return 1
    if urgency == "medium":
        return 2
    return 3


def _task_id(
    *,
    client_key: str,
    entity_type: str,
    entity_id: str,
    task_type: str,
    version_key: str,
) -> str:
    raw = "|".join([client_key, entity_type, entity_id, task_type, version_key]).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@router.get("/admin/ops/inbox", response_model=InboxResponse)
def get_ops_inbox(
    limit: int = Query(30, ge=1, le=30),
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    ensure_admin_ops_v1_enabled()
    settings = get_settings()

    tasks: list[InboxTaskOut] = []

    projects_view = build_projects_view(
        db,
        attention_only=True,
        limit=limit * 3,
    )
    for item in projects_view.get("items", []):
        client_key = str(item.get("client_key") or "unknown")
        entity_id = str(item.get("id") or "")
        if not entity_id:
            continue

        next_action = item.get("next_best_action") or {}
        task_type = str(next_action.get("type") or "review_attention")
        version_key = str(item.get("updated_at") or item.get("last_activity") or "")
        urgency = str(item.get("urgency") or "low")
        if urgency not in {"high", "medium", "low"}:
            flags = item.get("attention_flags") or []
            if "pending_confirmation" in flags:
                urgency = "high"
            elif "failed_outbox" in flags:
                urgency = "medium"
            else:
                urgency = "low"

        created_at = item.get("created_at")
        preferred_slot = item.get("estimate_preferred_slot")
        client_display_name = item.get("client_display_name") or "-"
        tasks.append(
            InboxTaskOut(
                task_id=_task_id(
                    client_key=client_key,
                    entity_type="project",
                    entity_id=entity_id,
                    task_type=task_type,
                    version_key=version_key,
                ),
                entity_type="project",
                entity_id=entity_id,
                client_key=client_key if client_key != "unknown" else None,
                task_type=task_type,
                title=client_display_name,
                reason=str(item.get("stuck_reason") or "Reikia sprendimo"),
                action_key=str(next_action.get("type") or "open_client"),
                payload={
                    "project_id": entity_id,
                    "client_key": client_key if client_key != "unknown" else None,
                    "created_at": created_at,
                    "preferred_slot_start": preferred_slot,
                    "client_display_name": client_display_name,
                },
                priority=_task_priority(urgency),
                urgency=urgency,
                updated_at=item.get("updated_at") or item.get("last_activity"),
            )
        )

    held_rows = db.execute(
        select(Appointment, Project)
        .outerjoin(Project, Project.id == Appointment.project_id)
        .where(Appointment.status == "HELD")
        .order_by(Appointment.starts_at.asc(), Appointment.id.asc())
        .limit(limit)
    ).all()
    for appt, project in held_rows:
        client_key = "unknown"
        if project is not None:
            client_key, _ = derive_client_key(project.client_info if isinstance(project.client_info, dict) else None)
        entity_id = str(appt.id)
        version_key = _iso_utc(appt.updated_at) or ""

        tasks.append(
            InboxTaskOut(
                task_id=_task_id(
                    client_key=client_key,
                    entity_type="appointment",
                    entity_id=entity_id,
                    task_type="confirm_hold",
                    version_key=version_key,
                ),
                entity_type="appointment",
                entity_id=entity_id,
                client_key=client_key if client_key != "unknown" else None,
                task_type="confirm_hold",
                title="Nepatvirtintas vizito rezervavimas",
                reason="HELD rezervacija laukia ADMIN patvirtinimo",
                action_key="confirm_hold",
                payload={
                    "appointment_id": entity_id,
                    "project_id": str(appt.project_id) if appt.project_id else None,
                },
                priority=1,
                urgency="high",
                updated_at=version_key,
            )
        )

    if settings.enable_call_assistant:
        new_calls = (
            db.execute(
                select(CallRequest)
                .where(CallRequest.status == "NEW")
                .order_by(desc(CallRequest.updated_at), desc(CallRequest.id))
                .limit(limit)
            )
            .scalars()
            .all()
        )
        for call in new_calls:
            client_key, _ = derive_client_key({"email": call.email, "phone": call.phone})
            entity_id = str(call.id)
            version_key = _iso_utc(call.updated_at) or _iso_utc(call.created_at) or ""
            tasks.append(
                InboxTaskOut(
                    task_id=_task_id(
                        client_key=client_key,
                        entity_type="call_request",
                        entity_id=entity_id,
                        task_type="review_new_call",
                        version_key=version_key,
                    ),
                    entity_type="call_request",
                    entity_id=entity_id,
                    client_key=client_key if client_key != "unknown" else None,
                    task_type="review_new_call",
                    title="Nauja skambucio uzklausa",
                    reason="Uzklausai reikia zmogaus sprendimo",
                    action_key="open_calls",
                    payload={"call_request_id": entity_id},
                    priority=1,
                    urgency="high",
                    updated_at=version_key,
                )
            )

    # Deterministic dedupe by task_id.
    deduped: dict[str, InboxTaskOut] = {}
    for task in tasks:
        deduped[task.task_id] = task

    sorted_tasks = sorted(
        deduped.values(),
        key=lambda t: (
            int(t.priority),
            t.updated_at or "",
            t.task_id,
        ),
    )

    return InboxResponse(
        items=sorted_tasks[:limit],
        generated_at=datetime.now(timezone.utc).isoformat(),
        limit=limit,
    )


class ProjectDayActionRequest(BaseModel):
    day: date
    action: str = Field(..., pattern="^(check_in|complete|upload_photo)$")
    note: str | None = Field(default=None, max_length=500)


@router.post("/admin/ops/project/{project_id}/day-action")
def project_day_action(
    project_id: str,
    payload: ProjectDayActionRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    ensure_admin_ops_v1_enabled()

    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projektas nerastas")

    action_map = {
        "check_in": "ADMIN_DAY_CHECK_IN",
        "complete": "ADMIN_DAY_COMPLETE",
        "upload_photo": "ADMIN_DAY_UPLOAD_PHOTO",
    }
    action_code = action_map[payload.action]

    create_audit_log(
        db,
        entity_type="project",
        entity_id=str(project.id),
        action=action_code,
        old_value=None,
        new_value=None,
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={
            "day": payload.day.isoformat(),
            "note": payload.note or "",
            "source": "admin_project_day_view",
        },
    )
    db.commit()
    return {"success": True, "project_id": str(project.id), "action": payload.action}


class ProposalActionRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|edit|escalate)$")
    note: str | None = Field(default=None, max_length=500)
    project_id: str | None = None


@router.post("/admin/ops/client/{client_key}/proposal-action")
def client_proposal_action(
    client_key: str,
    payload: ProposalActionRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    ensure_admin_ops_v1_enabled()

    create_audit_log(
        db,
        entity_type="system",
        entity_id=SYSTEM_ENTITY_ID,
        action="ADMIN_CLIENT_PROPOSAL_ACTION",
        old_value=None,
        new_value={
            "client_key": client_key,
            "action": payload.action,
            "project_id": payload.project_id,
        },
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={
            "note": payload.note or "",
            "source": "admin_client_card",
        },
    )
    db.commit()
    return {"success": True, "client_key": client_key, "action": payload.action}


class ClientCardSummaryOut(BaseModel):
    client_key: str
    display_name: str
    contact_masked: str
    stage: str
    deposit_state: str
    next_visit: str | None = None
    earned_total: float
    total_projects: int
    attention_flags: list[str] = Field(default_factory=list)


class ClientCardProposalOut(BaseModel):
    type: str | None = None
    label: str | None = None
    project_id: str | None = None
    confidence: float | None = None
    reason: str | None = None


class ClientCardSectionItem(BaseModel):
    id: str
    data: dict[str, Any]


class ClientCardResponse(BaseModel):
    summary: ClientCardSummaryOut
    proposal: ClientCardProposalOut
    dry_run: dict[str, Any]
    feature_flags: dict[str, bool] = {}
    pricing_project_id: str | None = None
    ai_pricing: dict[str, Any] | None = None
    ai_pricing_meta: dict[str, Any] | None = None
    ai_pricing_decision: dict[str, Any] | None = None
    extended_survey: dict[str, Any] | None = None
    projects: list[ClientCardSectionItem]
    payments: list[ClientCardSectionItem]
    calls: list[ClientCardSectionItem]
    photos: list[ClientCardSectionItem]
    timeline: list[ClientCardSectionItem]


def _sorted_projects_for_client(db: Session, client_key: str) -> list[Project]:
    projects = db.execute(select(Project).order_by(desc(Project.updated_at), desc(Project.id))).scalars().all()
    matched: list[Project] = []
    for p in projects:
        ck, _ = derive_client_key(p.client_info if isinstance(p.client_info, dict) else None)
        if ck == client_key:
            matched.append(p)
    return matched


def _proposal_confidence_and_reason(nba: dict[str, Any] | None, attention_flags: list[str]) -> tuple[float | None, str]:
    if not nba:
        return None, "No next action"
    action_type = str(nba.get("type") or "")
    if action_type in {"record_deposit", "record_final"}:
        return 0.9, "Payment action is deterministic from project state"
    if action_type in {"schedule_visit", "assign_expert"}:
        return 0.8, "Operational action inferred from project pipeline state"
    if "pending_confirmation" in attention_flags:
        return 0.75, "Pending confirmation flag requires manual decision"
    return 0.7, "Derived from current attention flags and status"


def _proposal_dry_run(nba: dict[str, Any] | None) -> dict[str, Any]:
    if not nba:
        return {"action": "none", "preview": None}
    action_type = str(nba.get("type") or "")
    project_id = str(nba.get("project_id") or "")
    if action_type == "record_deposit":
        return {
            "action": action_type,
            "preview": {"mode": "redirect", "url": f"/admin/projects#manual-deposit-{project_id}"},
        }
    if action_type == "record_final":
        return {
            "action": action_type,
            "preview": {"mode": "redirect", "url": f"/admin/projects#manual-final-{project_id}"},
        }
    if action_type == "schedule_visit":
        return {"action": action_type, "preview": {"mode": "redirect", "url": "/admin/calendar"}}
    if action_type == "resend_confirmation":
        return {"action": action_type, "preview": {"mode": "redirect", "url": f"/admin/projects#{project_id}"}}
    return {"action": action_type, "preview": {"mode": "manual"}}


def _next_visit(projects: list[Project]) -> str | None:
    scheduled = [p.scheduled_for for p in projects if p.scheduled_for]
    if not scheduled:
        return None
    ordered = sorted(scheduled)
    return _iso_utc(ordered[0])


def _emails_phones_from_projects(projects: list[Project]) -> tuple[set[str], set[str]]:
    emails: set[str] = set()
    phones: set[str] = set()
    for project in projects:
        ci = project.client_info if isinstance(project.client_info, dict) else {}
        raw_email = str(ci.get("email") or "").strip().lower()
        raw_phone = str(ci.get("phone") or "").strip()
        if raw_email:
            emails.add(raw_email)
        if raw_phone:
            phones.add(raw_phone)
    return emails, phones


@router.get("/admin/ops/client/{client_key}/card", response_model=ClientCardResponse)
def get_ops_client_card(
    client_key: str,
    projects_limit: int = Query(10, ge=1, le=50),
    payments_limit: int = Query(30, ge=1, le=100),
    calls_limit: int = Query(20, ge=1, le=100),
    photos_limit: int = Query(30, ge=1, le=100),
    timeline_limit: int = Query(50, ge=1, le=150),
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    ensure_admin_ops_v1_enabled()
    settings = get_settings()

    profile = build_customer_profile(db, client_key, settings=settings)
    if profile is None:
        raise HTTPException(status_code=404, detail="Klientas nerastas")

    projects = _sorted_projects_for_client(db, client_key)
    project_ids = [p.id for p in projects]
    profile_projects = profile.get("projects", [])
    next_action = profile.get("next_best_action")
    attention_flags = profile.get("attention_flags") or []
    stage = str(profile_projects[0]["status"]) if profile_projects else "-"
    deposit_state = str(profile_projects[0].get("deposit_state") or "-") if profile_projects else "-"
    confidence, reason = _proposal_confidence_and_reason(next_action, attention_flags)

    summary = ClientCardSummaryOut(
        client_key=client_key,
        display_name=str((profile.get("client_info") or {}).get("display_name") or "-"),
        contact_masked=str((profile.get("client_info") or {}).get("contact_masked") or "-"),
        stage=stage,
        deposit_state=deposit_state,
        next_visit=_next_visit(projects),
        earned_total=float((profile.get("summary") or {}).get("total_paid") or 0),
        total_projects=int((profile.get("summary") or {}).get("total_projects") or len(profile_projects)),
        attention_flags=[str(x) for x in attention_flags],
    )

    proposal = ClientCardProposalOut(
        type=str(next_action.get("type")) if isinstance(next_action, dict) and next_action.get("type") else None,
        label=str(next_action.get("label")) if isinstance(next_action, dict) and next_action.get("label") else None,
        project_id=str(next_action.get("project_id"))
        if isinstance(next_action, dict) and next_action.get("project_id")
        else None,
        confidence=confidence,
        reason=reason,
    )
    dry_run = _proposal_dry_run(next_action if isinstance(next_action, dict) else None)

    target_project: Project | None = None
    if isinstance(next_action, dict) and next_action.get("project_id"):
        wanted = str(next_action.get("project_id"))
        target_project = next((p for p in projects if str(p.id) == wanted), None)
    if target_project is None and projects:
        target_project = projects[0]

    pricing_project_id: str | None = str(target_project.id) if target_project else None
    ai_pricing: dict[str, Any] | None = None
    ai_pricing_meta: dict[str, Any] | None = None
    ai_pricing_decision: dict[str, Any] | None = None
    extended_survey: dict[str, Any] | None = None
    if target_project is not None:
        target_va = target_project.vision_analysis if isinstance(target_project.vision_analysis, dict) else {}
        target_ci = target_project.client_info if isinstance(target_project.client_info, dict) else {}
        raw_pricing = target_va.get("ai_pricing")
        raw_meta = target_va.get("ai_pricing_meta")
        raw_decision = target_va.get("ai_pricing_decision")
        raw_survey = target_ci.get("extended_survey")
        if isinstance(raw_pricing, dict):
            ai_pricing = raw_pricing
        if isinstance(raw_meta, dict):
            ai_pricing_meta = raw_meta
        if isinstance(raw_decision, dict):
            ai_pricing_decision = raw_decision
        if isinstance(raw_survey, dict):
            extended_survey = raw_survey

    # Batch: appointments for all projects
    appt_by_project: dict[str, list[dict]] = {}
    if project_ids:
        appt_rows = (
            db.execute(
                select(Appointment)
                .where(Appointment.project_id.in_(project_ids), Appointment.status != "CANCELLED")
                .order_by(Appointment.starts_at.asc())
            )
            .scalars()
            .all()
        )
        for appt in appt_rows:
            pid = str(appt.project_id)
            label = appt.starts_at.strftime("%Y-%m-%d %H:%M") if appt.starts_at else None
            appt_by_project.setdefault(pid, []).append(
                {
                    "visit_type": appt.visit_type or "PRIMARY",
                    "status": appt.status,
                    "starts_at": appt.starts_at.isoformat() if appt.starts_at else None,
                    "label": label,
                }
            )

    # Batch: expenses from finance ledger (gated by flag)
    expenses_by_project: dict[str, dict] = {}
    if settings.enable_finance_ledger and project_ids:
        expense_rows = db.execute(
            select(
                FinanceLedgerEntry.project_id,
                FinanceLedgerEntry.category,
                sa_func.sum(FinanceLedgerEntry.amount).label("total"),
            )
            .where(
                FinanceLedgerEntry.project_id.in_(project_ids),
                FinanceLedgerEntry.entry_type.in_(["EXPENSE", "TAX"]),
            )
            .group_by(FinanceLedgerEntry.project_id, FinanceLedgerEntry.category)
        ).all()
        for row in expense_rows:
            pid = str(row.project_id)
            entry = expenses_by_project.setdefault(pid, {"total": 0.0, "categories": {}})
            amt = float(row.total or 0)
            entry["categories"][row.category] = amt
            entry["total"] = round(entry["total"] + amt, 2)

    projects_by_id = {str(p.id): p for p in projects}

    project_items: list[ClientCardSectionItem] = []
    for p_view in profile_projects[:projects_limit]:
        pid = str(p_view.get("id") or "")
        p_orm = projects_by_id.get(pid)

        # Estimate (from client_info — 0 DB queries)
        estimate_data = None
        if p_orm:
            est = build_estimate_info(p_orm)
            if est:
                d = est.model_dump()
                d["phone"] = mask_phone(d.get("phone") or "")
                estimate_data = d

        # Payments (build_payments_summary — 2 small queries)
        payments_data = build_payments_summary(p_orm, db).model_dump() if p_orm else None

        # Documents (pure computation — 0 DB)
        docs_data = [d.model_dump() for d in get_documents_for_status(p_orm)] if p_orm else None

        # Visits (from batch)
        visits_data = appt_by_project.get(pid, [])

        # Expenses (from batch, gated)
        expenses_data = expenses_by_project.get(pid) if settings.enable_finance_ledger else None

        project_items.append(
            ClientCardSectionItem(
                id=pid,
                data={
                    "status": p_view.get("status"),
                    "deposit_state": p_view.get("deposit_state"),
                    "final_state": p_view.get("final_state"),
                    "updated_at": p_view.get("updated_at"),
                    "actions_available": p_view.get("actions_available") or [],
                    "area_m2": p_view.get("area_m2"),
                    "estimate": estimate_data,
                    "payments_summary": payments_data,
                    "documents": docs_data,
                    "visits": visits_data,
                    "expenses": expenses_data,
                },
            )
        )

    payment_items: list[ClientCardSectionItem] = []
    if project_ids:
        payment_rows = (
            db.execute(
                select(Payment)
                .where(Payment.project_id.in_(project_ids))
                .order_by(desc(Payment.received_at), desc(Payment.created_at), desc(Payment.id))
                .limit(payments_limit)
            )
            .scalars()
            .all()
        )
        for p in payment_rows:
            payment_items.append(
                ClientCardSectionItem(
                    id=str(p.id),
                    data={
                        "project_id": str(p.project_id),
                        "payment_type": p.payment_type,
                        "amount": float(p.amount) if p.amount is not None else None,
                        "currency": p.currency,
                        "status": p.status,
                        "payment_method": p.payment_method,
                        "received_at": _iso_utc(p.received_at),
                    },
                )
            )

    call_items: list[ClientCardSectionItem] = []
    if settings.enable_call_assistant and projects:
        emails, phones = _emails_phones_from_projects(projects)
        call_stmt = select(CallRequest)
        conds = []
        if emails:
            conds.append(CallRequest.email.in_(list(emails)))
        if phones:
            conds.append(CallRequest.phone.in_(list(phones)))
        if conds:
            call_rows = (
                db.execute(
                    call_stmt.where(or_(*conds))
                    .order_by(desc(CallRequest.updated_at), desc(CallRequest.id))
                    .limit(calls_limit)
                )
                .scalars()
                .all()
            )
            for c in call_rows:
                call_items.append(
                    ClientCardSectionItem(
                        id=str(c.id),
                        data={
                            "status": c.status,
                            "source": c.source,
                            "preferred_channel": c.preferred_channel,
                            "contact_masked": f"{mask_email(c.email)} / {mask_phone(c.phone)}",
                            "created_at": _iso_utc(c.created_at),
                            "updated_at": _iso_utc(c.updated_at),
                        },
                    )
                )

    photo_items: list[ClientCardSectionItem] = []
    if project_ids:
        photo_rows = (
            db.execute(
                select(Evidence)
                .where(and_(Evidence.project_id.is_not(None), Evidence.project_id.in_(project_ids)))
                .order_by(desc(Evidence.created_at), desc(Evidence.id))
                .limit(photos_limit)
            )
            .scalars()
            .all()
        )
        for ev in photo_rows:
            photo_items.append(
                ClientCardSectionItem(
                    id=str(ev.id),
                    data={
                        "project_id": str(ev.project_id),
                        "category": ev.category,
                        "file_url": ev.file_url,
                        "thumbnail_url": ev.thumbnail_url,
                        "medium_url": ev.medium_url,
                        "uploaded_at": _iso_utc(ev.uploaded_at),
                    },
                )
            )

    timeline_items: list[ClientCardSectionItem] = []
    if project_ids:
        timeline_rows = (
            db.execute(
                select(AuditLog)
                .where(and_(AuditLog.entity_type == "project", AuditLog.entity_id.in_(project_ids)))
                .order_by(desc(AuditLog.timestamp), desc(AuditLog.id))
                .limit(timeline_limit)
            )
            .scalars()
            .all()
        )
        for row in timeline_rows:
            timeline_items.append(
                ClientCardSectionItem(
                    id=str(row.id),
                    data={
                        "entity_id": str(row.entity_id),
                        "action": row.action,
                        "actor_type": row.actor_type,
                        "timestamp": _iso_utc(row.timestamp),
                        "metadata": row.audit_meta if isinstance(row.audit_meta, dict) else None,
                    },
                )
            )

    card_feature_flags: dict[str, bool] = {
        "ai_pricing": getattr(settings, "enable_ai_pricing", False),
        "finance_ledger": getattr(settings, "enable_finance_ledger", False),
    }

    return ClientCardResponse(
        summary=summary,
        proposal=proposal,
        dry_run=dry_run,
        feature_flags=card_feature_flags,
        pricing_project_id=pricing_project_id,
        ai_pricing=ai_pricing,
        ai_pricing_meta=ai_pricing_meta,
        ai_pricing_decision=ai_pricing_decision,
        extended_survey=extended_survey,
        projects=project_items,
        payments=payment_items,
        calls=call_items[:calls_limit],
        photos=photo_items[:photos_limit],
        timeline=timeline_items[:timeline_limit],
    )


# ─── Final quote (admin sets final price for DRAFT projects) ─────────────


@router.post("/admin/ops/project/{project_id}/final-quote")
def post_final_quote(
    project_id: str,
    payload: AdminFinalQuoteRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    ensure_admin_ops_v1_enabled()

    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projektas nerastas")
    if project.status != "DRAFT":
        raise HTTPException(status_code=400, detail="Galutine kaina galima tik DRAFT projektams")

    ci = dict(project.client_info) if isinstance(project.client_info, dict) else {}
    if not ci.get("quote_pending"):
        raise HTTPException(status_code=400, detail="Galutine kaina jau nustatyta (quote_pending=false)")

    ci["quote_pending"] = False
    actual_area = payload.actual_area_m2
    final_rate = round(payload.final_total_eur / actual_area, 2) if actual_area > 0 else 0
    ci["final_quote"] = {
        "service": payload.service,
        "method": payload.method,
        "actual_area_m2": actual_area,
        "final_total_eur": payload.final_total_eur,
        "notes": payload.notes,
        "admin_decided_at": datetime.now(timezone.utc).isoformat(),
    }
    estimate = ci.get("estimate")
    if isinstance(estimate, dict):
        estimate["final_rate_eur_m2"] = final_rate

    project.client_info = ci
    project.total_price_client = payload.final_total_eur
    project.area_m2 = actual_area
    db.add(project)

    create_audit_log(
        db,
        entity_type="project",
        entity_id=str(project.id),
        action="FINAL_QUOTE_SET",
        old_value=None,
        new_value={
            "final_total_eur": payload.final_total_eur,
            "actual_area_m2": actual_area,
            "quote_pending": False,
        },
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return {"ok": True}
