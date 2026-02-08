"""add thumbnail_url and medium_url to evidences

Revision ID: 20260208_000013
Revises: 20260208_000012
Create Date: 2026-02-08 14:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260208_000013"
down_revision = "20260208_000012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evidences", sa.Column("thumbnail_url", sa.Text(), nullable=True))
    op.add_column("evidences", sa.Column("medium_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("evidences", "medium_url")
    op.drop_column("evidences", "thumbnail_url")
