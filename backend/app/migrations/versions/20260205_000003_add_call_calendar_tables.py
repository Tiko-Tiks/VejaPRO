"""add call assistant and calendar tables

Revision ID: 20260205_000003
Revises: 20260203_000002
Create Date: 2026-02-05 00:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260205_000003"
down_revision = "20260203_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "call_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=255)),
        sa.Column("preferred_time", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'NEW'"),
        ),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'public'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_call_requests_status", "call_requests", ["status"])
    op.create_index("idx_call_requests_created", "call_requests", ["created_at"])

    op.create_table(
        "appointments",
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
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "call_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("call_requests.id", ondelete="SET NULL"),
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'SCHEDULED'"),
        ),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_appointments_status", "appointments", ["status"])
    op.create_index("idx_appointments_starts", "appointments", ["starts_at"])
    op.create_index("idx_appointments_project", "appointments", ["project_id"])
    op.create_index("idx_appointments_call_request", "appointments", ["call_request_id"])


def downgrade() -> None:
    op.drop_index("idx_appointments_call_request", table_name="appointments")
    op.drop_index("idx_appointments_project", table_name="appointments")
    op.drop_index("idx_appointments_starts", table_name="appointments")
    op.drop_index("idx_appointments_status", table_name="appointments")
    op.drop_table("appointments")

    op.drop_index("idx_call_requests_created", table_name="call_requests")
    op.drop_index("idx_call_requests_status", table_name="call_requests")
    op.drop_table("call_requests")
