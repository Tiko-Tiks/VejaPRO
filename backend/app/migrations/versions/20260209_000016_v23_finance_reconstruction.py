"""v23_finance_reconstruction

Revision ID: 20260209_000016
Revises: 20260209_000015
Create Date: 2026-02-09

V2.3 Finance Module Reconstruction:
- payments.ai_extracted_data JSONB column
- UNIQUE(provider, provider_event_id) idempotency index
- client_confirmations channel default sms -> email
- payment_method CHECK constraint
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql


revision = "20260209_000016"
down_revision = "20260209_000015"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def _index_exists(index_name: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :name"),
        {"name": index_name},
    )
    return result.scalar() is not None


def _constraint_exists(table: str, constraint_name: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        text(
            "SELECT 1 FROM information_schema.table_constraints WHERE table_name = :table AND constraint_name = :name"
        ),
        {"table": table, "name": constraint_name},
    )
    return result.scalar() is not None


def upgrade() -> None:
    # 1. payments.ai_extracted_data JSONB NULL
    if not _column_exists("payments", "ai_extracted_data"):
        op.add_column(
            "payments",
            sa.Column("ai_extracted_data", postgresql.JSONB, nullable=True),
        )

    # 2. UNIQUE(provider, provider_event_id) — idempotency index
    #    Partial index: only where provider_event_id IS NOT NULL
    if not _index_exists("uniq_payments_provider_event"):
        # Safety: check for duplicates first
        bind = op.get_bind()
        dupes = bind.execute(
            text(
                "SELECT provider, provider_event_id, COUNT(*) "
                "FROM payments "
                "WHERE provider_event_id IS NOT NULL "
                "GROUP BY provider, provider_event_id "
                "HAVING COUNT(*) > 1"
            )
        ).fetchall()
        if dupes:
            # Log duplicates but still create index — dedupe oldest keeping newest
            for provider, event_id, cnt in dupes:
                bind.execute(
                    text(
                        "DELETE FROM payments "
                        "WHERE id IN ("
                        "  SELECT id FROM payments "
                        "  WHERE provider = :provider "
                        "    AND provider_event_id = :event_id "
                        "  ORDER BY created_at ASC "
                        "  LIMIT :limit"
                        ")"
                    ),
                    {"provider": provider, "event_id": event_id, "limit": cnt - 1},
                )

        op.execute(
            "CREATE UNIQUE INDEX uniq_payments_provider_event "
            "ON payments(provider, provider_event_id) "
            "WHERE provider_event_id IS NOT NULL"
        )

    # 3. client_confirmations: channel default sms -> email
    op.alter_column(
        "client_confirmations",
        "channel",
        server_default=sa.text("'email'"),
    )

    # 4. payment_method CHECK constraint (safe: NOT VALID then VALIDATE)
    if not _constraint_exists("payments", "chk_payment_method_values"):
        op.execute(
            "ALTER TABLE payments ADD CONSTRAINT chk_payment_method_values "
            "CHECK (payment_method IS NULL OR payment_method IN "
            "('CASH','BANK_TRANSFER','CARD','WAIVED','OTHER')) "
            "NOT VALID"
        )
        op.execute("ALTER TABLE payments VALIDATE CONSTRAINT chk_payment_method_values")


def downgrade() -> None:
    # 4. Drop payment_method CHECK
    if _constraint_exists("payments", "chk_payment_method_values"):
        op.drop_constraint("chk_payment_method_values", "payments", type_="check")

    # 3. Revert channel default to sms
    op.alter_column(
        "client_confirmations",
        "channel",
        server_default=sa.text("'sms'"),
    )

    # 2. Drop UNIQUE index
    if _index_exists("uniq_payments_provider_event"):
        op.execute("DROP INDEX uniq_payments_provider_event")

    # 1. Drop ai_extracted_data column
    if _column_exists("payments", "ai_extracted_data"):
        op.drop_column("payments", "ai_extracted_data")
