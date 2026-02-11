"""service_requests (Client UI V3)

Revision ID: 20260211_000017
Revises: 20260209_000016
Create Date: 2026-02-11

Client UI V3: service_requests table for add-on / maintenance requests.
Status flow: NEW -> IN_REVIEW -> QUOTED -> SCHEDULED -> DONE | CLOSED.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260211_000017"
down_revision = "20260209_000016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("client_user_id", sa.String(64), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("service_slug", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'NEW'")),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('NEW','IN_REVIEW','QUOTED','SCHEDULED','DONE','CLOSED')",
            name="chk_service_request_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_service_requests_client", "service_requests", ["client_user_id"])
    op.create_index("idx_service_requests_project", "service_requests", ["project_id"])


def downgrade() -> None:
    op.drop_index("idx_service_requests_project", table_name="service_requests")
    op.drop_index("idx_service_requests_client", table_name="service_requests")
    op.drop_table("service_requests")
