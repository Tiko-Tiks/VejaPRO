"""add project indexes

Revision ID: 20260203_000002
Revises: 20260203_000001
Create Date: 2026-02-03 16:00:00
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260203_000002"
down_revision = "20260203_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX idx_projects_created_at ON projects (created_at DESC)")
    op.create_index("idx_projects_is_certified", "projects", ["is_certified"])


def downgrade() -> None:
    op.drop_index("idx_projects_is_certified", table_name="projects")
    op.execute("DROP INDEX IF EXISTS idx_projects_created_at")
