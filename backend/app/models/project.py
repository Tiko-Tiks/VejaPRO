import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.types import CHAR, TypeDecorator

Base = declarative_base()


class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value if dialect.name == "postgresql" else str(value)
        if isinstance(value, str):
            try:
                parsed = uuid.UUID(value)
            except ValueError:
                return value
            return parsed if dialect.name == "postgresql" else str(parsed)
        return value

    def process_result_value(self, value, dialect):
        if value is None or isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(value)
        except ValueError:
            return value


UUID_TYPE = GUID()
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
INET_TYPE = String(45).with_variant(INET, "postgresql")


class User(Base):
    __tablename__ = "users"

    id = Column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    email = Column(String(255), nullable=False, unique=True)
    phone = Column(String(20))
    role = Column(String(32), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Margin(Base):
    __tablename__ = "margins"

    id = Column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    service_type = Column(String(64), nullable=False)
    margin_percent = Column(Numeric(5, 2), nullable=False)
    valid_from = Column(DateTime(timezone=True), server_default=func.now())
    valid_until = Column(DateTime(timezone=True))
    created_by = Column(UUID_TYPE, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Project(Base):
    __tablename__ = "projects"

    id = Column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    client_info = Column(JSON_TYPE, nullable=False)
    status = Column(String(32), nullable=False, default="DRAFT", server_default=text("'DRAFT'"))
    area_m2 = Column(Numeric(10, 2))
    total_price_client = Column(Numeric(12, 2))
    internal_cost = Column(Numeric(12, 2))
    vision_analysis = Column(JSON_TYPE)
    has_robot = Column(Boolean, default=False, server_default=text("false"), nullable=False)
    is_certified = Column(Boolean, default=False, server_default=text("false"), nullable=False)
    marketing_consent = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    marketing_consent_at = Column(DateTime(timezone=True))
    status_changed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    assigned_contractor_id = Column(UUID_TYPE, ForeignKey("users.id"))
    assigned_expert_id = Column(UUID_TYPE, ForeignKey("users.id"))
    scheduled_for = Column(DateTime(timezone=True))
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(UUID_TYPE, nullable=False)
    action = Column(String(64), nullable=False)
    old_value = Column(JSON_TYPE)
    new_value = Column(JSON_TYPE)
    actor_type = Column(String(50), nullable=False)
    actor_id = Column(UUID_TYPE)
    ip_address = Column(INET_TYPE)
    user_agent = Column(Text)
    audit_meta = Column("metadata", JSON_TYPE, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    project_id = Column(UUID_TYPE, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(32), nullable=False, default="stripe", server_default=text("'stripe'"))
    provider_intent_id = Column(String(128))
    provider_event_id = Column(String(128))
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), nullable=False)
    payment_type = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    raw_payload = Column(JSON_TYPE)
    payment_method = Column(String(32))
    received_at = Column(DateTime(timezone=True))
    collected_by = Column(UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"))
    collection_context = Column(String(32))
    receipt_no = Column(String(64))
    proof_url = Column(Text)
    ai_extracted_data = Column(JSON_TYPE)
    is_manual_confirmed = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    confirmed_by = Column(UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ClientConfirmation(Base):
    __tablename__ = "client_confirmations"

    id = Column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    project_id = Column(UUID_TYPE, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    confirmed_at = Column(DateTime(timezone=True))
    confirmed_from_phone = Column(String(20))
    channel = Column(String(20), nullable=False, default="email", server_default=text("'email'"))
    status = Column(String(32), nullable=False, default="PENDING", server_default=text("'PENDING'"))
    attempts = Column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Evidence(Base):
    __tablename__ = "evidences"

    id = Column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    project_id = Column(UUID_TYPE, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    call_request_id = Column(UUID_TYPE, ForeignKey("call_requests.id", ondelete="SET NULL"))
    file_url = Column(Text, nullable=False)
    thumbnail_url = Column(Text)
    medium_url = Column(Text)
    category = Column(String(32), nullable=False)
    uploaded_by = Column(UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    show_on_web = Column(Boolean, default=False, server_default=text("false"), nullable=False)
    is_featured = Column(Boolean, default=False, server_default=text("false"), nullable=False)
    location_tag = Column(String(128))


class CallRequest(Base):
    __tablename__ = "call_requests"

    id = Column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name = Column(String(128), nullable=False)
    phone = Column(String(32), nullable=False)
    email = Column(String(255))
    preferred_time = Column(DateTime(timezone=True))
    notes = Column(Text)
    status = Column(String(32), nullable=False, default="NEW", server_default=text("'NEW'"))
    source = Column(String(32), nullable=False, default="public", server_default=text("'public'"))
    converted_project_id = Column(UUID_TYPE, ForeignKey("projects.id", ondelete="SET NULL"))
    preferred_channel = Column(String(20), nullable=False, default="email", server_default=text("'email'"))
    intake_state = Column(JSON_TYPE, nullable=False, default=dict, server_default=text("'{}'"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="chk_appointment_time"),
        CheckConstraint(
            "(project_id IS NOT NULL OR call_request_id IS NOT NULL)",
            name="chk_appt_link",
        ),
        CheckConstraint(
            "status IN ('HELD','CONFIRMED','CANCELLED')",
            name="chk_appointment_status_axis",
        ),
        CheckConstraint(
            "((status = 'HELD' AND hold_expires_at IS NOT NULL) OR (status <> 'HELD' AND hold_expires_at IS NULL))",
            name="chk_hold_only_when_held",
        ),
    )

    id = Column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    project_id = Column(UUID_TYPE, ForeignKey("projects.id", ondelete="SET NULL"))
    call_request_id = Column(UUID_TYPE, ForeignKey("call_requests.id", ondelete="SET NULL"))
    resource_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"))
    visit_type = Column(String(32), nullable=False, default="PRIMARY", server_default=text("'PRIMARY'"))
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    # Schedule Engine planning axis: HELD / CONFIRMED / CANCELLED only.
    status = Column(
        String(32),
        nullable=False,
        default="CONFIRMED",
        server_default=text("'CONFIRMED'"),
    )
    lock_level = Column(SmallInteger, nullable=False, default=0, server_default=text("0"))
    locked_at = Column(DateTime(timezone=True))
    locked_by = Column(UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"))
    lock_reason = Column(Text)
    hold_expires_at = Column(DateTime(timezone=True))
    weather_class = Column(String(32), nullable=False, default="MIXED", server_default=text("'MIXED'"))
    route_date = Column(Date)
    route_sequence = Column(Integer)
    row_version = Column(Integer, nullable=False, default=1, server_default=text("1"))
    superseded_by_id = Column(UUID_TYPE, ForeignKey("appointments.id", ondelete="SET NULL"))
    cancelled_at = Column(DateTime(timezone=True))
    cancelled_by = Column(UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"))
    cancel_reason = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ConversationLock(Base):
    __tablename__ = "conversation_locks"
    __table_args__ = (
        UniqueConstraint("channel", "conversation_id", name="uniq_conversation_lock"),
        Index("idx_conv_lock_exp", "hold_expires_at"),
        Index("idx_conv_lock_visit", "appointment_id", "visit_type"),
    )

    id = Column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    channel = Column(String(16), nullable=False)
    conversation_id = Column(String(128), nullable=False)
    appointment_id = Column(UUID_TYPE, ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False)
    visit_type = Column(String(32), nullable=False, default="PRIMARY", server_default=text("'PRIMARY'"))
    hold_expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ProjectScheduling(Base):
    __tablename__ = "project_scheduling"

    project_id = Column(UUID_TYPE, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    ready_to_schedule = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    default_weather_class = Column(String(32), nullable=False, default="MIXED", server_default=text("'MIXED'"))
    estimated_duration_min = Column(Integer, nullable=False)
    priority_score = Column(Integer, nullable=False, default=0, server_default=text("0"))
    preferred_time_windows = Column(JSON_TYPE)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SchedulePreview(Base):
    __tablename__ = "schedule_previews"
    __table_args__ = (
        Index("idx_schedule_preview_exp", "expires_at"),
        Index("idx_schedule_preview_route_resource", "route_date", "resource_id"),
    )

    id = Column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    route_date = Column(Date, nullable=False)
    resource_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    preview_hash = Column(String(128), nullable=False)
    payload = Column(JSON_TYPE, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True))
    created_by = Column(UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uniq_notification_outbox_dedupe_key"),
        Index("idx_notification_outbox_status_next", "status", "next_attempt_at"),
    )

    id = Column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(UUID_TYPE, nullable=False)

    channel = Column(String(32), nullable=False)  # sms / whatsapp / telegram / email
    template_key = Column(String(64), nullable=False)
    payload_json = Column(JSON_TYPE, nullable=False)
    dedupe_key = Column(String(128), nullable=False)

    status = Column(String(16), nullable=False, default="PENDING", server_default=text("'PENDING'"))
    attempt_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    next_attempt_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    sent_at = Column(DateTime(timezone=True))
    last_error = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class FinanceLedgerEntry(Base):
    __tablename__ = "finance_ledger_entries"
    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_ledger_amount_positive"),
        CheckConstraint(
            "entry_type IN ('EXPENSE','TAX','ADJUSTMENT')",
            name="chk_ledger_entry_type",
        ),
        Index("idx_fle_project", "project_id"),
        Index("idx_fle_entry_type", "entry_type"),
    )

    id = Column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    project_id = Column(UUID_TYPE, ForeignKey("projects.id", ondelete="SET NULL"))
    entry_type = Column(String(32), nullable=False)  # EXPENSE, TAX, ADJUSTMENT
    category = Column(String(64), nullable=False)  # FUEL, REPAIR, MATERIALS, etc.
    description = Column(Text)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), nullable=False, default="EUR", server_default=text("'EUR'"))
    payment_method = Column(String(32))  # CASH, BANK_TRANSFER, CARD, OTHER
    document_id = Column(UUID_TYPE, ForeignKey("finance_documents.id", ondelete="SET NULL"))
    reverses_entry_id = Column(UUID_TYPE, ForeignKey("finance_ledger_entries.id", ondelete="SET NULL"))
    recorded_by = Column(UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"))
    occurred_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceDocument(Base):
    __tablename__ = "finance_documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('NEW','EXTRACTED','READY','NEEDS_REVIEW','POSTED','REJECTED','DUPLICATE')",
            name="chk_findoc_status",
        ),
        Index("idx_findoc_status", "status"),
        Index("idx_findoc_file_hash", "file_hash"),
    )

    id = Column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    file_url = Column(Text, nullable=False)
    file_hash = Column(String(128))  # SHA-256 for deduplication
    original_filename = Column(String(256))
    status = Column(String(32), nullable=False, default="NEW", server_default=text("'NEW'"))
    uploaded_by = Column(UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class FinanceDocumentExtraction(Base):
    __tablename__ = "finance_document_extractions"

    id = Column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    document_id = Column(
        UUID_TYPE,
        ForeignKey("finance_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    extracted_json = Column(JSON_TYPE, nullable=False)
    confidence = Column(Numeric(5, 4))
    model_version = Column(String(64))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceVendorRule(Base):
    __tablename__ = "finance_vendor_rules"
    __table_args__ = (UniqueConstraint("vendor_pattern", name="uniq_vendor_pattern"),)

    id = Column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    vendor_pattern = Column(String(256), nullable=False)
    default_category = Column(String(64), nullable=False)
    default_entry_type = Column(String(32), nullable=False, default="EXPENSE", server_default=text("'EXPENSE'"))
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_by = Column(UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
