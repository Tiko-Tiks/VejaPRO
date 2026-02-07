"""add evidences.created_at

Revision ID: 20260206_000004
Revises: 20260205_000003
Create Date: 2026-02-06 00:45:00
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260206_000004"
down_revision = "20260205_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE evidences ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()")


def downgrade() -> None:
    op.execute("ALTER TABLE evidences DROP COLUMN IF EXISTS created_at")
