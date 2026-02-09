"""unified_client_card_v22

Revision ID: 20260209_000015
Revises: 20260208_000014
Create Date: 2026-02-09

Adds Unified Lead Card fields to call_requests, evidence linking,
renames sms_confirmations → client_confirmations, and adds indexes.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = "20260209_000015"
down_revision = "20260208_000014"
branch_labels = None
depends_on = None


def _has_column(conn: sa.Connection, table_name: str, column_name: str) -> bool:
    insp = inspect(conn)
    cols = [c["name"] for c in insp.get_columns(table_name)]
    return column_name in cols


def _has_table(conn: sa.Connection, table_name: str) -> bool:
    insp = inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    # ──────────────────────────────────────────────
    # 1) call_requests: Unified Lead Card columns
    # ──────────────────────────────────────────────

    if not _has_column(conn, "call_requests", "converted_project_id"):
        if dialect == "postgresql":
            op.add_column(
                "call_requests",
                sa.Column(
                    "converted_project_id",
                    postgresql.UUID(as_uuid=True),
                    sa.ForeignKey("projects.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )
        else:
            op.add_column(
                "call_requests",
                sa.Column(
                    "converted_project_id",
                    sa.CHAR(36),
                    sa.ForeignKey("projects.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )

    if not _has_column(conn, "call_requests", "preferred_channel"):
        op.add_column(
            "call_requests",
            sa.Column(
                "preferred_channel",
                sa.String(length=20),
                nullable=False,
                server_default="email",
            ),
        )

    if not _has_column(conn, "call_requests", "intake_state"):
        if dialect == "postgresql":
            op.add_column(
                "call_requests",
                sa.Column(
                    "intake_state",
                    postgresql.JSONB(),
                    nullable=False,
                    server_default=sa.text("'{}'::jsonb"),
                ),
            )
        else:
            op.add_column(
                "call_requests",
                sa.Column(
                    "intake_state",
                    sa.JSON(),
                    nullable=False,
                    server_default=sa.text("'{}'"),
                ),
            )

    # ──────────────────────────────────────────────
    # 2) evidences: link to call_request + nullable project_id
    # ──────────────────────────────────────────────

    if not _has_column(conn, "evidences", "call_request_id"):
        if dialect == "postgresql":
            op.add_column(
                "evidences",
                sa.Column(
                    "call_request_id",
                    postgresql.UUID(as_uuid=True),
                    sa.ForeignKey("call_requests.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )
        else:
            op.add_column(
                "evidences",
                sa.Column(
                    "call_request_id",
                    sa.CHAR(36),
                    sa.ForeignKey("call_requests.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )

    # Make evidences.project_id nullable (was NOT NULL before)
    if dialect == "postgresql":
        op.execute("ALTER TABLE evidences ALTER COLUMN project_id DROP NOT NULL")

    # ──────────────────────────────────────────────
    # 3) sms_confirmations → client_confirmations
    # ──────────────────────────────────────────────

    if _has_table(conn, "sms_confirmations") and not _has_table(conn, "client_confirmations"):
        op.rename_table("sms_confirmations", "client_confirmations")

        # Add channel column
        if not _has_column(conn, "client_confirmations", "channel"):
            op.add_column(
                "client_confirmations",
                sa.Column(
                    "channel",
                    sa.String(length=20),
                    nullable=False,
                    server_default="sms",
                ),
            )

        if dialect == "postgresql":
            # Rename indexes
            op.execute("ALTER INDEX IF EXISTS idx_sms_project RENAME TO idx_cc_project")
            op.execute("ALTER INDEX IF EXISTS idx_sms_token_hash RENAME TO idx_cc_token_hash")

            # Update RLS policy references (table name changed)
            op.execute(
                "DO $$ BEGIN "
                "IF EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'client_confirmations' AND policyname = 'service_role_all') THEN "
                "NULL; "  # Policy already exists or was auto-renamed
                "END IF; "
                "END $$"
            )

    # ──────────────────────────────────────────────
    # 4) Indexes (Postgres only)
    # ──────────────────────────────────────────────

    if dialect == "postgresql":
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_call_requests_email_lower
            ON call_requests (lower(email))
            WHERE email IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_call_requests_intake_state_gin
            ON call_requests USING gin (intake_state)
            """
        )
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_evidences_call_request_id
            ON evidences (call_request_id)
            WHERE call_request_id IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uniq_call_request_confirmed_visit
            ON appointments(call_request_id, visit_type)
            WHERE status = 'CONFIRMED' AND call_request_id IS NOT NULL
            """
        )


def downgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    # Drop indexes
    if dialect == "postgresql":
        op.execute("DROP INDEX IF EXISTS uniq_call_request_confirmed_visit")
        op.execute("DROP INDEX IF EXISTS idx_evidences_call_request_id")
        op.execute("DROP INDEX IF EXISTS idx_call_requests_intake_state_gin")
        op.execute("DROP INDEX IF EXISTS idx_call_requests_email_lower")

    # Revert client_confirmations → sms_confirmations
    if _has_table(conn, "client_confirmations"):
        if _has_column(conn, "client_confirmations", "channel"):
            op.drop_column("client_confirmations", "channel")

        if dialect == "postgresql":
            op.execute("ALTER INDEX IF EXISTS idx_cc_project RENAME TO idx_sms_project")
            op.execute("ALTER INDEX IF EXISTS idx_cc_token_hash RENAME TO idx_sms_token_hash")

        op.rename_table("client_confirmations", "sms_confirmations")

    # Revert evidences
    if dialect == "postgresql":
        # Re-add NOT NULL (only safe if all rows have project_id)
        op.execute("ALTER TABLE evidences ALTER COLUMN project_id SET NOT NULL")

    if _has_column(conn, "evidences", "call_request_id"):
        op.drop_column("evidences", "call_request_id")

    # Revert call_requests
    if _has_column(conn, "call_requests", "intake_state"):
        op.drop_column("call_requests", "intake_state")
    if _has_column(conn, "call_requests", "preferred_channel"):
        op.drop_column("call_requests", "preferred_channel")
    if _has_column(conn, "call_requests", "converted_project_id"):
        op.drop_column("call_requests", "converted_project_id")
