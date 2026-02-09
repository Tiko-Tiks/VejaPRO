"""notification outbox (v1)

Revision ID: 20260207_000009
Revises: 20260207_000008
Create Date: 2026-02-07 19:10:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260207_000009"
down_revision = "20260207_000008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB, "postgresql")

    op.create_table(
        "notification_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("template_key", sa.String(length=64), nullable=False),
        sa.Column("payload_json", json_type, nullable=False),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column(
            "attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("dedupe_key", name="uniq_notification_outbox_dedupe_key"),
    )

    op.create_index(
        "idx_notification_outbox_status_next",
        "notification_outbox",
        ["status", "next_attempt_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_notification_outbox_status_next", table_name="notification_outbox"
    )
    op.drop_table("notification_outbox")
