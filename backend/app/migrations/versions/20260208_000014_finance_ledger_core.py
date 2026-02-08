"""finance ledger core tables

Revision ID: 20260208_000014
Revises: 20260208_000013
Create Date: 2026-02-08 18:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260208_000014"
down_revision = "20260208_000013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- finance_documents (must come before ledger entries due to FK) ---
    op.create_table(
        "finance_documents",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("file_hash", sa.String(128)),
        sa.Column("original_filename", sa.String(256)),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'NEW'")),
        sa.Column(
            "uploaded_by", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('NEW','EXTRACTED','READY','NEEDS_REVIEW','POSTED','REJECTED','DUPLICATE')",
            name="chk_findoc_status",
        ),
    )
    op.create_index("idx_findoc_status", "finance_documents", ["status"])
    op.create_index("idx_findoc_file_hash", "finance_documents", ["file_hash"])

    # --- finance_ledger_entries ---
    op.create_table(
        "finance_ledger_entries",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL")
        ),
        sa.Column("entry_type", sa.String(32), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("payment_method", sa.String(32)),
        sa.Column(
            "document_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("finance_documents.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "reverses_entry_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("finance_ledger_entries.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "recorded_by", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="chk_ledger_amount_positive"),
        sa.CheckConstraint(
            "entry_type IN ('EXPENSE','TAX','ADJUSTMENT')",
            name="chk_ledger_entry_type",
        ),
    )
    op.create_index("idx_fle_project", "finance_ledger_entries", ["project_id"])
    op.create_index("idx_fle_entry_type", "finance_ledger_entries", ["entry_type"])

    # --- finance_document_extractions ---
    op.create_table(
        "finance_document_extractions",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("finance_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("extracted_json", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4)),
        sa.Column("model_version", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- finance_vendor_rules ---
    op.create_table(
        "finance_vendor_rules",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("vendor_pattern", sa.String(256), nullable=False),
        sa.Column("default_category", sa.String(64), nullable=False),
        sa.Column("default_entry_type", sa.String(32), nullable=False, server_default=sa.text("'EXPENSE'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_by", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("vendor_pattern", name="uniq_vendor_pattern"),
    )


def downgrade() -> None:
    op.drop_table("finance_vendor_rules")
    op.drop_table("finance_document_extractions")
    op.drop_index("idx_fle_entry_type", table_name="finance_ledger_entries")
    op.drop_index("idx_fle_project", table_name="finance_ledger_entries")
    op.drop_table("finance_ledger_entries")
    op.drop_index("idx_findoc_file_hash", table_name="finance_documents")
    op.drop_index("idx_findoc_status", table_name="finance_documents")
    op.drop_table("finance_documents")
