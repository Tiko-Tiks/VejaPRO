"""init core schema

Revision ID: 20260203_000001
Revises: 
Create Date: 2026-02-03 00:50:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260203_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")


    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("phone", sa.String(length=20)),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index("idx_users_role", "users", ["role"])

    op.create_table(
        "margins",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("service_type", sa.String(length=64), nullable=False),
        sa.Column("margin_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_margins_service", "margins", ["service_type"])
    op.create_index("idx_margins_valid", "margins", ["valid_from", "valid_until"])
    op.execute("CREATE UNIQUE INDEX idx_margins_active ON margins (service_type) WHERE valid_until IS NULL")

    op.create_table(
        "projects",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("client_info", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'DRAFT'"),
        ),
        sa.Column("area_m2", sa.Numeric(10, 2)),
        sa.Column("total_price_client", sa.Numeric(12, 2)),
        sa.Column("internal_cost", sa.Numeric(12, 2)),
        sa.Column("vision_analysis", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("has_robot", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_certified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("marketing_consent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("marketing_consent_at", sa.DateTime(timezone=True)),
        sa.Column("status_changed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("assigned_contractor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("assigned_expert_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("scheduled_for", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("marketing_consent = FALSE OR marketing_consent_at IS NOT NULL", name="chk_marketing_consent_at"),
        sa.CheckConstraint("(is_certified = TRUE AND status IN ('CERTIFIED','ACTIVE')) OR (is_certified = FALSE AND status NOT IN ('CERTIFIED','ACTIVE'))", name="chk_is_certified"),
    )

    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("actor_type", sa.String(length=50), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("ip_address", sa.dialects.postgresql.INET()),
        sa.Column("user_agent", sa.Text()),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "payments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default=sa.text("'stripe'")),
        sa.Column("provider_intent_id", sa.String(length=128)),
        sa.Column("provider_event_id", sa.String(length=128)),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("payment_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_payments_event", "payments", ["provider", "provider_event_id"], unique=True)
    op.create_index("idx_payments_project", "payments", ["project_id"])

    op.create_table(
        "sms_confirmations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("confirmed_from_phone", sa.String(length=20)),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_sms_project", "sms_confirmations", ["project_id"])
    op.create_index("idx_sms_token_hash", "sms_confirmations", ["token_hash"])

    op.create_table(
        "evidences",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True)),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("show_on_web", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("location_tag", sa.String(length=128)),
    )

    op.create_index("idx_audit_action", "audit_logs", ["action"])
    op.create_index("idx_audit_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("idx_audit_timestamp", "audit_logs", ["timestamp"])
    op.create_index("idx_evidences_project", "evidences", ["project_id"])
    op.create_index("idx_evidences_category", "evidences", ["category"])
    op.create_index("idx_projects_status", "projects", ["status"])
    op.execute("CREATE INDEX idx_evidences_gallery ON evidences (show_on_web, is_featured, uploaded_at DESC)")
    op.execute("CREATE INDEX idx_evidences_location ON evidences (location_tag, show_on_web, uploaded_at DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_evidences_location")
    op.execute("DROP INDEX IF EXISTS idx_evidences_gallery")
    op.drop_index("idx_projects_status", table_name="projects")
    op.drop_index("idx_evidences_category", table_name="evidences")
    op.drop_index("idx_evidences_project", table_name="evidences")
    op.drop_index("idx_audit_timestamp", table_name="audit_logs")
    op.drop_index("idx_audit_entity", table_name="audit_logs")
    op.drop_index("idx_audit_action", table_name="audit_logs")
    op.drop_table("evidences")
    op.drop_table("sms_confirmations")
    op.drop_table("payments")
    op.drop_table("audit_logs")
    op.drop_table("projects")
    op.drop_table("margins")
    op.drop_table("users")
