"""payments-first manual patch (v1.5.1)

Revision ID: 20260207_000008
Revises: 20260207_000007
Create Date: 2026-02-07 16:40:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260207_000008"
down_revision = "20260207_000007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.add_column("payments", sa.Column("payment_method", sa.String(length=32), nullable=True))
    op.add_column("payments", sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payments", sa.Column("collected_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("payments", sa.Column("collection_context", sa.String(length=32), nullable=True))
    op.add_column("payments", sa.Column("receipt_no", sa.String(length=64), nullable=True))
    op.add_column("payments", sa.Column("proof_url", sa.Text(), nullable=True))
    op.add_column(
        "payments",
        sa.Column("is_manual_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("payments", sa.Column("confirmed_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("payments", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_foreign_key(
        "fk_payments_collected_by", "payments", "users", ["collected_by"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_payments_confirmed_by", "payments", "users", ["confirmed_by"], ["id"], ondelete="SET NULL"
    )

    if is_postgres:
        # Optional: help avoid duplicates when receipt_no is used as human id.
        op.create_index(
            "uniq_payments_manual_receipt",
            "payments",
            ["provider", "receipt_no"],
            unique=True,
            postgresql_where=sa.text("provider='manual' AND receipt_no IS NOT NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.drop_index("uniq_payments_manual_receipt", table_name="payments")

    op.drop_constraint("fk_payments_confirmed_by", "payments", type_="foreignkey")
    op.drop_constraint("fk_payments_collected_by", "payments", type_="foreignkey")

    op.drop_column("payments", "confirmed_at")
    op.drop_column("payments", "confirmed_by")
    op.drop_column("payments", "is_manual_confirmed")
    op.drop_column("payments", "proof_url")
    op.drop_column("payments", "receipt_no")
    op.drop_column("payments", "collection_context")
    op.drop_column("payments", "collected_by")
    op.drop_column("payments", "received_at")
    op.drop_column("payments", "payment_method")
