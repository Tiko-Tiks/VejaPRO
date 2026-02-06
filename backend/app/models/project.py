import uuid

from sqlalchemy import Column, String, Boolean, DateTime, Numeric, Text, ForeignKey, Integer, text, JSON
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB, INET
from sqlalchemy.sql import func
from sqlalchemy.orm import declarative_base

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

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    email = Column(String(255), nullable=False, unique=True)
    phone = Column(String(20))
    role = Column(String(32), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Margin(Base):
    __tablename__ = "margins"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    service_type = Column(String(64), nullable=False)
    margin_percent = Column(Numeric(5, 2), nullable=False)
    valid_from = Column(DateTime(timezone=True), server_default=func.now())
    valid_until = Column(DateTime(timezone=True))
    created_by = Column(UUID_TYPE, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    client_info = Column(JSON_TYPE, nullable=False)
    status = Column(String(32), nullable=False, default="DRAFT", server_default=text("'DRAFT'"))
    area_m2 = Column(Numeric(10, 2))
    total_price_client = Column(Numeric(12, 2))
    internal_cost = Column(Numeric(12, 2))
    vision_analysis = Column(JSON_TYPE)
    has_robot = Column(Boolean, default=False, server_default=text("false"))
    is_certified = Column(Boolean, default=False, server_default=text("false"))
    marketing_consent = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    marketing_consent_at = Column(DateTime(timezone=True))
    status_changed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    assigned_contractor_id = Column(UUID_TYPE, ForeignKey("users.id"))
    assigned_expert_id = Column(UUID_TYPE, ForeignKey("users.id"))
    scheduled_for = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(UUID_TYPE, nullable=False)
    action = Column(String(64), nullable=False)
    old_value = Column(JSON_TYPE)
    new_value = Column(JSON_TYPE)
    actor_type = Column(String(50), nullable=False)
    actor_id = Column(UUID_TYPE)
    ip_address = Column(INET_TYPE)
    user_agent = Column(Text)
    meta = Column("metadata", JSON_TYPE, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    project_id = Column(UUID_TYPE, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(32), nullable=False, default="stripe", server_default=text("'stripe'"))
    provider_intent_id = Column(String(128))
    provider_event_id = Column(String(128))
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), nullable=False)
    payment_type = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    raw_payload = Column(JSON_TYPE)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SmsConfirmation(Base):
    __tablename__ = "sms_confirmations"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    project_id = Column(UUID_TYPE, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    confirmed_at = Column(DateTime(timezone=True))
    confirmed_from_phone = Column(String(20))
    status = Column(String(32), nullable=False, default="PENDING", server_default=text("'PENDING'"))
    attempts = Column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Evidence(Base):
    __tablename__ = "evidences"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    project_id = Column(UUID_TYPE, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    file_url = Column(Text, nullable=False)
    category = Column(String(32), nullable=False)
    uploaded_by = Column(UUID_TYPE)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False)
    show_on_web = Column(Boolean, default=False, server_default=text("false"))
    is_featured = Column(Boolean, default=False, server_default=text("false"))
    location_tag = Column(String(128))


class CallRequest(Base):
    __tablename__ = "call_requests"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    name = Column(String(128), nullable=False)
    phone = Column(String(32), nullable=False)
    email = Column(String(255))
    preferred_time = Column(DateTime(timezone=True))
    notes = Column(Text)
    status = Column(String(32), nullable=False, default="NEW", server_default=text("'NEW'"))
    source = Column(String(32), nullable=False, default="public", server_default=text("'public'"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    project_id = Column(UUID_TYPE, ForeignKey("projects.id", ondelete="SET NULL"))
    call_request_id = Column(UUID_TYPE, ForeignKey("call_requests.id", ondelete="SET NULL"))
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(32), nullable=False, default="SCHEDULED", server_default=text("'SCHEDULED'"))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
