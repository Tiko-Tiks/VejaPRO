"""add foreign key indexes for performance

Revision ID: 20260206_000006
Revises: 20260206_000005
Create Date: 2026-02-06 13:05:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260206_000006"
down_revision = "20260206_000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add indexes for foreign keys that don't have covering indexes.
    # This improves JOIN performance and foreign key constraint checks.
    op.create_index("idx_margins_created_by", "margins", ["created_by"], unique=False)
    op.create_index(
        "idx_projects_assigned_contractor",
        "projects",
        ["assigned_contractor_id"],
        unique=False,
    )
    op.create_index(
        "idx_projects_assigned_expert", "projects", ["assigned_expert_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("idx_margins_created_by", table_name="margins")
    op.drop_index("idx_projects_assigned_contractor", table_name="projects")
    op.drop_index("idx_projects_assigned_expert", table_name="projects")
