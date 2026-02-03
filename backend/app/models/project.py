import uuid

from sqlalchemy import Column, String, Boolean, DateTime, Numeric, Text, ForeignKey, Integer, text
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.sql import func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    email = Column(String(255), nullable=False, unique=True)
    phone = Column(String(20))
    role = Column(String(32), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Margin(Base):
    __tablename__ = "margins"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    service_type = Column(String(64), nullable=False)
    margin_percent = Column(Numeric(5, 2), nullable=False)
    valid_from = Column(DateTime(timezone=True), server_default=func.now())
    valid_until = Column(DateTime(timezone=True))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    client_info = Column(JSONB, nullable=False)
    status = Column(String(32), nullable=False, default="DRAFT", server_default=text("'DRAFT'"))
    area_m2 = Column(Numeric(10, 2))
    total_price_client = Column(Numeric(12, 2))
    internal_cost = Column(Numeric(12, 2))
    vision_analysis = Column(JSONB)
    has_robot = Column(Boolean, default=False, server_default=text("false"))
    is_certified = Column(Boolean, default=False, server_default=text("false"))
    marketing_consent = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    marketing_consent_at = Column(DateTime(timezone=True))
    status_changed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    assigned_contractor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    assigned_expert_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    scheduled_for = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String(64), nullable=False)
    old_value = Column(JSONB)
    new_value = Column(JSONB)
    actor_type = Column(String(50), nullable=False)
    actor_id = Column(UUID(as_uuid=True))
    ip_address = Column(INET)
    user_agent = Column(Text)
    metadata = Column(JSONB)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(32), nullable=False, default="stripe", server_default=text("'stripe'"))
    provider_intent_id = Column(String(128))
    provider_event_id = Column(String(128))
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), nullable=False)
    payment_type = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    raw_payload = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SmsConfirmation(Base):
    __tablename__ = "sms_confirmations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    confirmed_at = Column(DateTime(timezone=True))
    confirmed_from_phone = Column(String(20))
    status = Column(String(32), nullable=False, default="PENDING", server_default=text("'PENDING'"))
    attempts = Column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Evidence(Base):
    __tablename__ = "evidences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    file_url = Column(Text, nullable=False)
    category = Column(String(32), nullable=False)
    uploaded_by = Column(UUID(as_uuid=True))
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    show_on_web = Column(Boolean, default=False, server_default=text("false"))
    is_featured = Column(Boolean, default=False, server_default=text("false"))
    location_tag = Column(String(128))
