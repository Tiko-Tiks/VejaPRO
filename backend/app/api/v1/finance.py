import asyncio
import base64
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.core.dependencies import get_db
from app.core.storage import build_object_url, get_storage_client
from app.models.project import (
    ClientConfirmation,
    FinanceDocument,
    FinanceDocumentExtraction,
    FinanceLedgerEntry,
    FinanceVendorRule,
    Payment,
    Project,
    User,
)
from app.schemas.finance import (
    BulkPostRequest,
    BulkPostResponse,
    DocumentExtractionOut,
    DocumentPostRequest,
    FinanceDocumentListResponse,
    FinanceDocumentOut,
    LedgerEntryCreate,
    LedgerEntryOut,
    LedgerListResponse,
    LedgerReverseRequest,
    PeriodFinanceSummary,
    ProjectFinanceSummary,
    QuickPaymentRequest,
    QuickPaymentResponse,
    VendorRuleCreate,
    VendorRuleListResponse,
    VendorRuleOut,
)
from app.schemas.project import ProjectStatus
from app.services.notification_outbox import enqueue_notification
from app.services.transition_service import (
    apply_transition,
    create_audit_log,
    create_client_confirmation,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _require_finance_enabled():
    settings = get_settings()
    if not settings.enable_finance_ledger:
        raise HTTPException(404, "Nerastas")


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _user_agent(request: Request) -> Optional[str]:
    return request.headers.get("user-agent") if request else None


def _user_fk_or_none(db: Session, user_id: str) -> uuid.UUID | None:
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        return None
    return user_uuid if db.get(User, user_uuid) else None


def _encode_cursor(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    payload = dt.isoformat().encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("utf-8")


def _decode_cursor(value: str) -> datetime:
    try:
        raw = base64.urlsafe_b64decode(value.encode("utf-8")).decode("utf-8")
        parsed = datetime.fromisoformat(raw)
    except Exception as exc:
        raise HTTPException(400, "Neteisingas žymeklis") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


# ---------------------------------------------------------------------------
# Ledger CRUD
# ---------------------------------------------------------------------------


@router.post("/admin/finance/ledger", response_model=LedgerEntryOut)
def create_ledger_entry(
    payload: LedgerEntryCreate,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("SUBCONTRACTOR", "ADMIN")),
    db: Session = Depends(get_db),
):
    _require_finance_enabled()

    entry = FinanceLedgerEntry(
        project_id=payload.project_id,
        entry_type=payload.entry_type.value,
        category=payload.category.value,
        description=payload.description or None,
        amount=payload.amount,
        currency=(payload.currency or "EUR").upper(),
        payment_method=payload.payment_method.value if payload.payment_method else None,
        document_id=payload.document_id,
        recorded_by=_user_fk_or_none(db, current_user.id),
        occurred_at=payload.occurred_at,
    )
    db.add(entry)
    db.flush()

    create_audit_log(
        db,
        entity_type="finance_ledger",
        entity_id=str(entry.id),
        action="FINANCE_LEDGER_ENTRY_CREATED",
        old_value=None,
        new_value={
            "entry_type": entry.entry_type,
            "category": entry.category,
            "amount": float(entry.amount),
            "project_id": str(entry.project_id) if entry.project_id else None,
        },
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    db.commit()
    db.refresh(entry)
    return _entry_to_out(entry)


@router.get("/admin/finance/ledger", response_model=LedgerListResponse)
def list_ledger_entries(
    project_id: Optional[str] = Query(None),
    entry_type: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_roles("SUBCONTRACTOR", "ADMIN")),
    db: Session = Depends(get_db),
):
    _require_finance_enabled()

    q = db.query(FinanceLedgerEntry)
    if project_id:
        q = q.filter(FinanceLedgerEntry.project_id == project_id)
    if entry_type:
        q = q.filter(FinanceLedgerEntry.entry_type == entry_type.upper())
    if cursor:
        cursor_dt = _decode_cursor(cursor)
        q = q.filter(FinanceLedgerEntry.created_at < cursor_dt)

    q = q.order_by(desc(FinanceLedgerEntry.created_at))
    rows = q.limit(limit + 1).all()

    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        if last.created_at:
            next_cursor = _encode_cursor(last.created_at)

    return LedgerListResponse(
        items=[_entry_to_out(e) for e in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.post("/admin/finance/ledger/{entry_id}/reverse", response_model=LedgerEntryOut)
def reverse_ledger_entry(
    entry_id: str,
    payload: LedgerReverseRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _require_finance_enabled()

    original = db.get(FinanceLedgerEntry, entry_id)
    if not original:
        raise HTTPException(404, "Įrašas nerastas")

    existing_reversal = (
        db.query(FinanceLedgerEntry)
        .filter(FinanceLedgerEntry.reverses_entry_id == entry_id)
        .first()
    )
    if existing_reversal:
        raise HTTPException(400, "Įrašas jau koreguotas")

    reversal = FinanceLedgerEntry(
        project_id=original.project_id,
        entry_type="ADJUSTMENT",
        category=original.category,
        description=payload.reason,
        amount=original.amount,
        currency=original.currency,
        payment_method=original.payment_method,
        reverses_entry_id=original.id,
        recorded_by=_user_fk_or_none(db, current_user.id),
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(reversal)
    db.flush()

    create_audit_log(
        db,
        entity_type="finance_ledger",
        entity_id=str(reversal.id),
        action="FINANCE_LEDGER_ENTRY_REVERSED",
        old_value={
            "original_entry_id": str(original.id),
            "amount": float(original.amount),
        },
        new_value={
            "reversal_entry_id": str(reversal.id),
            "reason": payload.reason,
        },
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    db.commit()
    db.refresh(reversal)
    return _entry_to_out(reversal)


# ---------------------------------------------------------------------------
# Reports / Summary
# ---------------------------------------------------------------------------


@router.get("/admin/finance/summary", response_model=PeriodFinanceSummary)
def finance_summary(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_roles("SUBCONTRACTOR", "ADMIN")),
    db: Session = Depends(get_db),
):
    _require_finance_enabled()

    period_start = (
        datetime.fromisoformat(start)
        if start
        else datetime(2020, 1, 1, tzinfo=timezone.utc)
    )
    period_end = datetime.fromisoformat(end) if end else datetime.now(timezone.utc)

    income = (
        db.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(
            Payment.status == "SUCCEEDED",
            Payment.provider.in_(["manual", "stripe"]),
            Payment.created_at >= period_start,
            Payment.created_at <= period_end,
        )
        .scalar()
    )

    total_expenses = (
        db.query(func.coalesce(func.sum(FinanceLedgerEntry.amount), 0))
        .filter(
            FinanceLedgerEntry.entry_type.in_(["EXPENSE", "TAX"]),
            FinanceLedgerEntry.created_at >= period_start,
            FinanceLedgerEntry.created_at <= period_end,
        )
        .scalar()
    )

    reversal_sum = (
        db.query(func.coalesce(func.sum(FinanceLedgerEntry.amount), 0))
        .filter(
            FinanceLedgerEntry.reverses_entry_id.isnot(None),
            FinanceLedgerEntry.created_at >= period_start,
            FinanceLedgerEntry.created_at <= period_end,
        )
        .scalar()
    )

    project_count = (
        db.query(func.count(func.distinct(Payment.project_id)))
        .filter(
            Payment.status == "SUCCEEDED",
            Payment.created_at >= period_start,
            Payment.created_at <= period_end,
        )
        .scalar()
    )

    income_f = float(income)
    expenses_f = float(total_expenses)
    reversal_f = float(reversal_sum)
    net = expenses_f - reversal_f

    return PeriodFinanceSummary(
        period_start=period_start,
        period_end=period_end,
        total_income=income_f,
        total_expenses=expenses_f,
        net_expenses=net,
        profit=income_f - net,
        project_count=project_count or 0,
    )


@router.get(
    "/admin/finance/projects/{project_id}", response_model=ProjectFinanceSummary
)
def project_finance(
    project_id: str,
    current_user: CurrentUser = Depends(require_roles("SUBCONTRACTOR", "ADMIN")),
    db: Session = Depends(get_db),
):
    _require_finance_enabled()

    income = (
        db.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(
            Payment.project_id == project_id,
            Payment.status == "SUCCEEDED",
            Payment.provider.in_(["manual", "stripe"]),
        )
        .scalar()
    )

    total_expenses = (
        db.query(func.coalesce(func.sum(FinanceLedgerEntry.amount), 0))
        .filter(
            FinanceLedgerEntry.project_id == project_id,
            FinanceLedgerEntry.entry_type.in_(["EXPENSE", "TAX"]),
        )
        .scalar()
    )

    reversal_sum = (
        db.query(func.coalesce(func.sum(FinanceLedgerEntry.amount), 0))
        .filter(
            FinanceLedgerEntry.project_id == project_id,
            FinanceLedgerEntry.reverses_entry_id.isnot(None),
        )
        .scalar()
    )

    income_f = float(income)
    expenses_f = float(total_expenses)
    reversal_f = float(reversal_sum)
    net = expenses_f - reversal_f

    return ProjectFinanceSummary(
        project_id=project_id,
        total_income=income_f,
        total_expenses=expenses_f,
        net_expenses=net,
        profit=income_f - net,
    )


# ---------------------------------------------------------------------------
# Quick Payment & Transition (composite endpoint)
# ---------------------------------------------------------------------------

BUCKET_FINANCE = "finance-documents"
MAX_FINANCE_DOC_BYTES = 15 * 1024 * 1024


@router.post(
    "/projects/{project_id}/quick-payment-and-transition",
    response_model=QuickPaymentResponse,
)
def quick_payment_and_transition(
    project_id: str,
    payload: QuickPaymentRequest,
    request: Request,
    current_user: CurrentUser = Depends(
        require_roles("SUBCONTRACTOR", "EXPERT", "ADMIN")
    ),
    db: Session = Depends(get_db),
):
    _require_finance_enabled()
    settings = get_settings()

    # V2.3: row-lock on project (SELECT ... FOR UPDATE)
    from sqlalchemy import select

    project = db.execute(
        select(Project).where(Project.id == project_id).with_for_update()
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Projektas nerastas")

    payment_type = payload.payment_type.upper()
    if payment_type not in ("DEPOSIT", "FINAL"):
        raise HTTPException(400, "payment_type turi būti DEPOSIT arba FINAL")

    if payment_type == "DEPOSIT" and project.status != ProjectStatus.DRAFT.value:
        raise HTTPException(400, "Deposit galimas tik DRAFT projektams")
    if payment_type == "FINAL" and project.status not in {
        ProjectStatus.CERTIFIED.value,
        ProjectStatus.ACTIVE.value,
    }:
        raise HTTPException(
            400, "Final mokėjimas galimas tik CERTIFIED/ACTIVE projektams"
        )

    # V2.3: Idempotency with 409 on conflict
    existing = (
        db.query(Payment)
        .filter(
            Payment.provider == "manual",
            Payment.provider_event_id == payload.provider_event_id,
        )
        .first()
    )
    if existing:
        amount_check = Decimal(str(payload.amount)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if (
            existing.payment_type == payment_type
            and str(existing.project_id) == str(project.id)
            and existing.amount == amount_check
        ):
            return QuickPaymentResponse(
                success=True,
                payment_id=str(existing.id),
                payment_type=existing.payment_type,
                amount=float(existing.amount),
                status_changed=False,
                new_status=project.status,
            )
        raise HTTPException(
            409, "provider_event_id jau panaudotas su kitais parametrais"
        )

    amount = Decimal(str(payload.amount)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    now = datetime.now(timezone.utc)

    payment = Payment(
        project_id=project.id,
        provider="manual",
        provider_event_id=payload.provider_event_id,
        amount=amount,
        currency=(payload.currency or "EUR").upper(),
        payment_type=payment_type,
        status="SUCCEEDED",
        raw_payload={"notes": payload.notes} if payload.notes else None,
        payment_method=(payload.payment_method or "CASH").upper(),
        received_at=payload.received_at or now,
        collected_by=_user_fk_or_none(db, current_user.id),
        collection_context=payload.collection_context,
        receipt_no=payload.receipt_no,
        proof_url=payload.proof_url,
        is_manual_confirmed=True,
        confirmed_by=_user_fk_or_none(db, current_user.id),
        confirmed_at=now,
    )
    db.add(payment)
    db.flush()

    create_audit_log(
        db,
        entity_type="payment",
        entity_id=str(payment.id),
        action="PAYMENT_RECORDED_MANUAL",
        old_value=None,
        new_value={
            "project_id": str(project.id),
            "payment_type": payment_type,
            "amount": float(amount),
            "currency": payload.currency,
            "payment_method": payload.payment_method,
        },
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )

    status_changed = False
    email_queued = False
    new_status = project.status

    if payload.transition_to:
        target = ProjectStatus(payload.transition_to)
        try:
            changed = apply_transition(
                db,
                project=project,
                new_status=target,
                actor_type=current_user.role,
                actor_id=current_user.id,
                ip_address=_client_ip(request),
                user_agent=_user_agent(request),
            )
            status_changed = changed
            new_status = project.status
        except HTTPException as exc:
            # Transition not allowed — payment still recorded
            logger.warning(
                "Transition to %s failed for project %s: %s",
                target,
                project_id,
                exc.detail,
            )
        except Exception as exc:
            # Unexpected error — payment still recorded
            logger.exception(
                "Unexpected transition error for project %s: %s", project_id, exc
            )

    # V2.3: FINAL -> email confirmation (not SMS)
    if payment_type == "FINAL" and project.status == ProjectStatus.CERTIFIED.value:
        client_email = None
        if isinstance(project.client_info, dict):
            client_email = project.client_info.get("email")

        if not settings.enable_email_intake or not client_email:
            create_audit_log(
                db,
                entity_type="project",
                entity_id=str(project.id),
                action="FIN_CHANNEL_UNAVAILABLE",
                old_value=None,
                new_value={
                    "reason": "no_email"
                    if not client_email
                    else "email_intake_disabled"
                },
                actor_type=current_user.role,
                actor_id=current_user.id,
                ip_address=_client_ip(request),
                user_agent=_user_agent(request),
            )
        else:
            token = create_client_confirmation(db, str(project.id), channel="email")
            create_audit_log(
                db,
                entity_type="project",
                entity_id=str(project.id),
                action="EMAIL_CONFIRMATION_CREATED",
                old_value=None,
                new_value={"token_hint": token[:4], "channel": "email"},
                actor_type=current_user.role,
                actor_id=current_user.id,
                ip_address=_client_ip(request),
                user_agent=_user_agent(request),
            )
            enqueue_notification(
                db,
                entity_type="project",
                entity_id=str(project.id),
                channel="email",
                template_key="FINAL_PAYMENT_CONFIRMATION",
                payload_json={
                    "to": client_email,
                    "subject": "VejaPRO - Patvirtinkite galutinį mokėjimą",
                    "body_text": f"Jūsų patvirtinimo kodas: {token}",
                },
            )
            email_queued = True

            # V2.3: optional WhatsApp ping
            if settings.enable_whatsapp_ping:
                whatsapp_consent = (project.client_info or {}).get(
                    "whatsapp_consent", False
                )
                phone = (project.client_info or {}).get("phone")
                if whatsapp_consent and phone:
                    enqueue_notification(
                        db,
                        entity_type="project",
                        entity_id=str(project.id),
                        channel="whatsapp_ping",
                        template_key="FINAL_PAYMENT_WHATSAPP_PING",
                        payload_json={
                            "to": phone,
                            "message": "Gavome mokėjimą. Patikrinkite el. paštą.",
                        },
                    )

    db.commit()

    return QuickPaymentResponse(
        success=True,
        payment_id=str(payment.id),
        payment_type=payment_type,
        amount=float(amount),
        status_changed=status_changed,
        new_status=new_status,
        email_queued=email_queued,
    )


# ---------------------------------------------------------------------------
# Documents (gated by ENABLE_FINANCE_AI_INGEST)
# ---------------------------------------------------------------------------


def _require_ai_ingest_enabled():
    settings = get_settings()
    if not settings.enable_finance_ai_ingest:
        raise HTTPException(404, "Nerastas")


@router.post("/admin/finance/documents", response_model=FinanceDocumentOut)
async def upload_finance_document(
    request: Request,
    file: UploadFile = File(...),
    notes: Optional[str] = Form(None),
    current_user: CurrentUser = Depends(require_roles("SUBCONTRACTOR", "ADMIN")),
    db: Session = Depends(get_db),
):
    _require_finance_enabled()
    _require_ai_ingest_enabled()

    content = await file.read()
    if not content:
        raise HTTPException(400, "Tuščias failas")
    if len(content) > MAX_FINANCE_DOC_BYTES:
        raise HTTPException(413, "Failas per didelis")

    # SHA-256 deduplication
    file_hash = hashlib.sha256(content).hexdigest()
    existing = (
        db.query(FinanceDocument).filter(FinanceDocument.file_hash == file_hash).first()
    )
    if existing and existing.status != "REJECTED":
        create_audit_log(
            db,
            entity_type="finance_document",
            entity_id=str(existing.id),
            action="FINANCE_DOCUMENT_DUPLICATE_DETECTED",
            old_value=None,
            new_value={"file_hash": file_hash, "original_id": str(existing.id)},
            actor_type=current_user.role,
            actor_id=current_user.id,
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )
        db.commit()
        raise HTTPException(
            409, f"Dublikatas: dokumentas jau egzistuoja (id={existing.id})"
        )

    # Upload to storage
    token = uuid.uuid4().hex
    ext = ""
    if file.filename:
        parts = file.filename.rsplit(".", 1)
        if len(parts) > 1:
            ext = f".{parts[1].lower()}"
    obj_path = f"finance/{token}{ext}"

    try:
        storage = get_storage_client()
        options = {"content-type": file.content_type} if file.content_type else None
        storage.storage.from_(BUCKET_FINANCE).upload(obj_path, content, options)
        file_url = build_object_url(BUCKET_FINANCE, obj_path)
    except Exception as exc:
        # Storage upload failed; fallback to relative path
        logger.error(
            "Finance document upload to storage failed: %s", exc, exc_info=True
        )
        file_url = f"/storage/{obj_path}"

    doc = FinanceDocument(
        file_url=file_url,
        file_hash=file_hash,
        original_filename=file.filename,
        status="NEW",
        uploaded_by=_user_fk_or_none(db, current_user.id),
        notes=notes,
    )
    db.add(doc)
    db.flush()

    create_audit_log(
        db,
        entity_type="finance_document",
        entity_id=str(doc.id),
        action="FINANCE_DOCUMENT_UPLOADED",
        old_value=None,
        new_value={"file_url": file_url, "file_hash": file_hash, "status": "NEW"},
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    db.commit()
    db.refresh(doc)
    return _doc_to_out(doc)


@router.get("/admin/finance/documents", response_model=FinanceDocumentListResponse)
def list_finance_documents(
    status: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_roles("SUBCONTRACTOR", "ADMIN")),
    db: Session = Depends(get_db),
):
    _require_finance_enabled()
    _require_ai_ingest_enabled()

    q = db.query(FinanceDocument)
    if status:
        q = q.filter(FinanceDocument.status == status.upper())
    if cursor:
        cursor_dt = _decode_cursor(cursor)
        q = q.filter(FinanceDocument.created_at < cursor_dt)

    q = q.order_by(desc(FinanceDocument.created_at))
    rows = q.limit(limit + 1).all()

    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        if last.created_at:
            next_cursor = _encode_cursor(last.created_at)

    return FinanceDocumentListResponse(
        items=[_doc_to_out(d) for d in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.post(
    "/admin/finance/documents/{document_id}/extract",
    response_model=DocumentExtractionOut,
)
async def extract_document(
    document_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _require_finance_enabled()
    _require_ai_ingest_enabled()

    doc = db.get(FinanceDocument, document_id)
    if not doc:
        raise HTTPException(404, "Dokumentas nerastas")

    # Vendor rules auto-matching: check filename against vendor patterns
    settings = get_settings()
    matched_rule = None
    if doc.original_filename and settings.enable_finance_auto_rules:
        name_lower = doc.original_filename.lower()
        rules = (
            db.query(FinanceVendorRule)
            .filter(FinanceVendorRule.is_active.is_(True))
            .all()
        )
        for rule in rules:
            if rule.vendor_pattern.lower() in name_lower:
                matched_rule = rule
                break

    extracted = {
        "entry_type": matched_rule.default_entry_type if matched_rule else "EXPENSE",
        "category": matched_rule.default_category if matched_rule else "OTHER",
        "vendor_match": matched_rule.vendor_pattern if matched_rule else None,
        "description": doc.original_filename or "",
        "amount": 0,
        "currency": "EUR",
    }
    model_version = "rules-v1" if matched_rule else "stub-v0"
    confidence = 0.8 if matched_rule else 0.0

    # V2.3: AI extraction (proposal-only — results stored for admin review)
    ai_extracted_data = None
    try:
        from app.services.ai.finance_extract.service import extract_finance_document

        ai_result = await extract_finance_document(doc.original_filename or "")
        ai_extracted_data = ai_result.model_dump()
        if ai_result.confidence > confidence:
            extracted["amount"] = ai_result.amount
            extracted["description"] = ai_result.description or extracted["description"]
            if ai_result.currency:
                extracted["currency"] = ai_result.currency
            confidence = ai_result.confidence
            model_version = ai_result.model_version
    except Exception as exc:
        # AI extraction is best-effort, vendor rules still apply
        logger.warning(
            "AI extraction failed for document %s: %s", document_id, exc, exc_info=True
        )

    extraction = FinanceDocumentExtraction(
        document_id=doc.id,
        extracted_json=extracted,
        confidence=confidence,
        model_version=model_version,
    )
    db.add(extraction)
    doc.status = "EXTRACTED"
    db.flush()

    create_audit_log(
        db,
        entity_type="finance_document",
        entity_id=str(doc.id),
        action="FINANCE_DOCUMENT_EXTRACTED",
        old_value={"status": "NEW"},
        new_value={
            "status": "EXTRACTED",
            "ai_extracted": ai_extracted_data is not None,
        },
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    db.commit()
    db.refresh(extraction)
    return DocumentExtractionOut(
        id=str(extraction.id),
        document_id=str(extraction.document_id),
        extracted_json=extraction.extracted_json,
        confidence=float(extraction.confidence) if extraction.confidence else None,
        model_version=extraction.model_version,
        created_at=extraction.created_at,
    )


@router.post(
    "/admin/finance/documents/{document_id}/post", response_model=LedgerEntryOut
)
def post_document_to_ledger(
    document_id: str,
    payload: DocumentPostRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _require_finance_enabled()
    _require_ai_ingest_enabled()

    doc = db.get(FinanceDocument, document_id)
    if not doc:
        raise HTTPException(404, "Dokumentas nerastas")

    if doc.status == "POSTED":
        raise HTTPException(400, "Dokumentas jau paskelbtas")
    if doc.status == "REJECTED":
        raise HTTPException(400, "Dokumentas atmestas")

    entry = FinanceLedgerEntry(
        project_id=payload.project_id,
        entry_type=payload.entry_type.value,
        category=payload.category.value,
        description=payload.description or None,
        amount=payload.amount,
        currency=(payload.currency or "EUR").upper(),
        payment_method=payload.payment_method.value if payload.payment_method else None,
        document_id=doc.id,
        recorded_by=_user_fk_or_none(db, current_user.id),
        occurred_at=payload.occurred_at,
    )
    db.add(entry)
    doc.status = "POSTED"
    db.flush()

    create_audit_log(
        db,
        entity_type="finance_document",
        entity_id=str(doc.id),
        action="FINANCE_DOCUMENT_POSTED",
        old_value=None,
        new_value={
            "ledger_entry_id": str(entry.id),
            "amount": float(entry.amount),
        },
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    db.commit()
    db.refresh(entry)
    return _entry_to_out(entry)


@router.post("/admin/finance/documents/bulk-post", response_model=BulkPostResponse)
def bulk_post_documents(
    payload: BulkPostRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _require_finance_enabled()
    _require_ai_ingest_enabled()

    posted = 0
    skipped = 0
    errors: list[str] = []

    for doc_id in payload.document_ids:
        doc = db.get(FinanceDocument, doc_id)
        if not doc:
            errors.append(f"{doc_id}: nerastas")
            continue
        if doc.status in ("POSTED", "REJECTED"):
            skipped += 1
            continue

        extraction = (
            db.query(FinanceDocumentExtraction)
            .filter(FinanceDocumentExtraction.document_id == doc.id)
            .order_by(desc(FinanceDocumentExtraction.created_at))
            .first()
        )
        if not extraction or not isinstance(extraction.extracted_json, dict):
            errors.append(f"{doc_id}: nėra ekstrakcijos")
            continue

        data = extraction.extracted_json
        entry = FinanceLedgerEntry(
            project_id=data.get("project_id"),
            entry_type=data.get("entry_type", "EXPENSE"),
            category=data.get("category", "OTHER"),
            description=data.get("description"),
            amount=float(data.get("amount", 0)) or 0.01,
            currency=data.get("currency", "EUR"),
            payment_method=data.get("payment_method"),
            document_id=doc.id,
            recorded_by=_user_fk_or_none(db, current_user.id),
        )
        db.add(entry)
        doc.status = "POSTED"
        posted += 1

    if posted > 0:
        db.flush()
        create_audit_log(
            db,
            entity_type="finance_document",
            entity_id="bulk",
            action="FINANCE_BULK_POST_EXECUTED",
            old_value=None,
            new_value={"posted": posted, "skipped": skipped, "errors": len(errors)},
            actor_type=current_user.role,
            actor_id=current_user.id,
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )

    db.commit()
    return BulkPostResponse(posted=posted, skipped=skipped, errors=errors)


# ---------------------------------------------------------------------------
# Vendor Rules
# ---------------------------------------------------------------------------


@router.post("/admin/finance/vendor-rules", response_model=VendorRuleOut)
def create_vendor_rule(
    payload: VendorRuleCreate,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _require_finance_enabled()

    existing = (
        db.query(FinanceVendorRule)
        .filter(FinanceVendorRule.vendor_pattern == payload.vendor_pattern)
        .first()
    )
    if existing:
        raise HTTPException(400, "Taisyklė jau egzistuoja")

    rule = FinanceVendorRule(
        vendor_pattern=payload.vendor_pattern,
        default_category=payload.default_category.value,
        default_entry_type=payload.default_entry_type.value,
        created_by=_user_fk_or_none(db, current_user.id),
    )
    db.add(rule)
    db.flush()

    create_audit_log(
        db,
        entity_type="finance_vendor_rule",
        entity_id=str(rule.id),
        action="FINANCE_VENDOR_RULE_CREATED",
        old_value=None,
        new_value={
            "vendor_pattern": rule.vendor_pattern,
            "category": rule.default_category,
        },
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    db.commit()
    db.refresh(rule)
    return _rule_to_out(rule)


@router.get("/admin/finance/vendor-rules", response_model=VendorRuleListResponse)
def list_vendor_rules(
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _require_finance_enabled()

    rules = (
        db.query(FinanceVendorRule)
        .filter(FinanceVendorRule.is_active.is_(True))
        .order_by(FinanceVendorRule.vendor_pattern)
        .all()
    )
    return VendorRuleListResponse(items=[_rule_to_out(r) for r in rules])


@router.delete("/admin/finance/vendor-rules/{rule_id}")
def delete_vendor_rule(
    rule_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    _require_finance_enabled()

    rule = db.get(FinanceVendorRule, rule_id)
    if not rule:
        raise HTTPException(404, "Taisyklė nerasta")

    rule.is_active = False
    create_audit_log(
        db,
        entity_type="finance_vendor_rule",
        entity_id=str(rule.id),
        action="FINANCE_VENDOR_RULE_DELETED",
        old_value={"is_active": True},
        new_value={"is_active": False},
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    db.commit()
    return {"success": True}


# ---------------------------------------------------------------------------
# V2.3: SSE Finance Metrics (aggregate-only, no PII)
# ---------------------------------------------------------------------------

_sse_active_connections = 0


def _compute_finance_metrics(db: Session) -> dict:
    """Compute aggregate finance metrics — no PII."""
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Daily volume
    daily_volume = float(
        db.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(Payment.status == "SUCCEEDED", Payment.created_at >= day_start)
        .scalar()
    )

    # Manual vs Stripe ratio
    manual_count = (
        db.query(func.count(Payment.id))
        .filter(Payment.provider == "manual", Payment.status == "SUCCEEDED")
        .scalar()
        or 0
    )
    stripe_count = (
        db.query(func.count(Payment.id))
        .filter(Payment.provider == "stripe", Payment.status == "SUCCEEDED")
        .scalar()
        or 0
    )
    total_payments = manual_count + stripe_count
    manual_ratio = (
        round(manual_count / total_payments, 3) if total_payments > 0 else 0.0
    )

    # Average confirmation attempts
    avg_attempts = float(
        db.query(func.coalesce(func.avg(ClientConfirmation.attempts), 0))
        .filter(ClientConfirmation.status.in_(["CONFIRMED", "FAILED", "EXPIRED"]))
        .scalar()
    )

    # Reject rate (FAILED + EXPIRED vs total completed confirmations)
    total_completed = (
        db.query(func.count(ClientConfirmation.id))
        .filter(ClientConfirmation.status.in_(["CONFIRMED", "FAILED", "EXPIRED"]))
        .scalar()
        or 0
    )
    rejected = (
        db.query(func.count(ClientConfirmation.id))
        .filter(ClientConfirmation.status.in_(["FAILED", "EXPIRED"]))
        .scalar()
        or 0
    )
    reject_rate = round(rejected / total_completed, 3) if total_completed > 0 else 0.0

    # Average confirm time (created_at -> confirmed_at)
    from sqlalchemy import extract

    avg_confirm_seconds = (
        db.query(
            func.coalesce(
                func.avg(
                    extract("epoch", ClientConfirmation.confirmed_at)
                    - extract("epoch", ClientConfirmation.created_at)
                ),
                0,
            )
        )
        .filter(
            ClientConfirmation.status == "CONFIRMED",
            ClientConfirmation.confirmed_at.isnot(None),
        )
        .scalar()
    )
    avg_confirm_time_minutes = (
        round(float(avg_confirm_seconds) / 60, 1) if avg_confirm_seconds else 0.0
    )

    return {
        "daily_volume": round(daily_volume, 2),
        "manual_count": manual_count,
        "stripe_count": stripe_count,
        "manual_ratio": manual_ratio,
        "avg_attempts": round(avg_attempts, 2),
        "reject_rate": reject_rate,
        "avg_confirm_time_minutes": avg_confirm_time_minutes,
        "total_confirmations": total_completed,
        "timestamp": now.isoformat(),
    }


@router.get("/admin/finance/metrics")
async def finance_metrics_sse(
    request: Request,
    current_user: CurrentUser = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    global _sse_active_connections

    settings = get_settings()
    if not settings.enable_finance_metrics:
        raise HTTPException(404, "Nerastas")

    if _sse_active_connections >= settings.finance_metrics_max_sse_connections:
        raise HTTPException(429, "Per daug aktyvių SSE jungčių")

    _sse_active_connections += 1

    async def event_stream():
        global _sse_active_connections
        try:
            while True:
                if await request.is_disconnected():
                    break
                metrics = _compute_finance_metrics(db)
                yield f"data: {json.dumps(metrics)}\n\n"
                await asyncio.sleep(5)
        finally:
            _sse_active_connections -= 1

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry_to_out(e: FinanceLedgerEntry) -> LedgerEntryOut:
    return LedgerEntryOut(
        id=str(e.id),
        project_id=str(e.project_id) if e.project_id else None,
        entry_type=e.entry_type,
        category=e.category,
        description=e.description,
        amount=float(e.amount),
        currency=e.currency,
        payment_method=e.payment_method,
        document_id=str(e.document_id) if e.document_id else None,
        reverses_entry_id=str(e.reverses_entry_id) if e.reverses_entry_id else None,
        recorded_by=str(e.recorded_by) if e.recorded_by else None,
        occurred_at=e.occurred_at,
        created_at=e.created_at,
    )


def _doc_to_out(d: FinanceDocument) -> FinanceDocumentOut:
    return FinanceDocumentOut(
        id=str(d.id),
        file_url=d.file_url,
        file_hash=d.file_hash,
        original_filename=d.original_filename,
        status=d.status,
        uploaded_by=str(d.uploaded_by) if d.uploaded_by else None,
        notes=d.notes,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def _rule_to_out(r: FinanceVendorRule) -> VendorRuleOut:
    return VendorRuleOut(
        id=str(r.id),
        vendor_pattern=r.vendor_pattern,
        default_category=r.default_category,
        default_entry_type=r.default_entry_type,
        is_active=bool(r.is_active),
        created_by=str(r.created_by) if r.created_by else None,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )
