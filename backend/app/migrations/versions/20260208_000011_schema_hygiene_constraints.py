"""schema hygiene: constraints + not-null + FK consistency

Revision ID: 20260208_000011
Revises: 20260207_000010
Create Date: 2026-02-08 00:20:00
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260208_000011"
down_revision = "20260207_000010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # These operations are Postgres-first. The project uses Postgres in production.
    # CI tests typically run against SQLite and may not apply Alembic migrations.
    if not is_postgres:
        return

    # 1) Ensure appointments always have a valid time range.
    # Add as NOT VALID first so we can get a clearer failure point during VALIDATE
    # if legacy data contains invalid rows.
    op.execute(
        "ALTER TABLE appointments "
        "ADD CONSTRAINT chk_appointment_time "
        "CHECK (ends_at > starts_at) NOT VALID"
    )
    op.execute("ALTER TABLE appointments VALIDATE CONSTRAINT chk_appointment_time")

    # 2) Fix NOT NULL drift for created_at/timestamp columns in core tables.
    # Backfill NULLs defensively before enforcing NOT NULL.
    op.execute("UPDATE users SET created_at = now() WHERE created_at IS NULL")
    op.execute("ALTER TABLE users ALTER COLUMN created_at SET NOT NULL")

    op.execute("UPDATE margins SET created_at = now() WHERE created_at IS NULL")
    op.execute("ALTER TABLE margins ALTER COLUMN created_at SET NOT NULL")

    op.execute("UPDATE payments SET created_at = now() WHERE created_at IS NULL")
    op.execute("ALTER TABLE payments ALTER COLUMN created_at SET NOT NULL")

    op.execute("UPDATE sms_confirmations SET created_at = now() WHERE created_at IS NULL")
    op.execute("ALTER TABLE sms_confirmations ALTER COLUMN created_at SET NOT NULL")

    op.execute("UPDATE audit_logs SET timestamp = now() WHERE timestamp IS NULL")
    op.execute("ALTER TABLE audit_logs ALTER COLUMN timestamp SET NOT NULL")

    # 3) Add FK for evidences.uploaded_by -> users.id (ON DELETE SET NULL).
    # If there is any bad legacy reference, NULL it out so constraint creation succeeds.
    op.execute(
        "UPDATE evidences "
        "SET uploaded_by = NULL "
        "WHERE uploaded_by IS NOT NULL "
        "AND uploaded_by NOT IN (SELECT id FROM users)"
    )
    op.create_foreign_key(
        "fk_evidences_uploaded_by_users",
        "evidences",
        "users",
        ["uploaded_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    if not is_postgres:
        return

    op.drop_constraint("fk_evidences_uploaded_by_users", "evidences", type_="foreignkey")

    # Revert NOT NULL tightening (schema hygiene rollback).
    op.execute("ALTER TABLE audit_logs ALTER COLUMN timestamp DROP NOT NULL")
    op.execute("ALTER TABLE sms_confirmations ALTER COLUMN created_at DROP NOT NULL")
    op.execute("ALTER TABLE payments ALTER COLUMN created_at DROP NOT NULL")
    op.execute("ALTER TABLE margins ALTER COLUMN created_at DROP NOT NULL")
    op.execute("ALTER TABLE users ALTER COLUMN created_at DROP NOT NULL")

    op.execute("ALTER TABLE appointments DROP CONSTRAINT IF EXISTS chk_appointment_time")
