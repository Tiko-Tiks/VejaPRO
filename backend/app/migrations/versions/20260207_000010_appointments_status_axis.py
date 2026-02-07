"""appointments status axis: schedule-engine only

Revision ID: 20260207_000010
Revises: 20260207_000009
Create Date: 2026-02-07 23:30:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260207_000010"
down_revision = "20260207_000009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Normalize legacy values:
    # - SCHEDULED -> CONFIRMED
    # - COMPLETED -> CANCELLED (planning axis only)
    # - anything else -> CANCELLED
    op.execute("UPDATE appointments SET status='CONFIRMED' WHERE status='SCHEDULED'")
    if is_postgres:
        op.execute(
            "UPDATE appointments "
            "SET status='CANCELLED', "
            "    cancel_reason=COALESCE(cancel_reason,'MIGRATED_FROM_COMPLETED'), "
            "    cancelled_at=COALESCE(cancelled_at, now()) "
            "WHERE status='COMPLETED'"
        )
        op.execute(
            "UPDATE appointments "
            "SET status='CANCELLED', "
            "    cancel_reason=COALESCE(cancel_reason,'MIGRATED_UNKNOWN_STATUS'), "
            "    cancelled_at=COALESCE(cancelled_at, now()), "
            "    hold_expires_at=NULL "
            "WHERE status NOT IN ('HELD','CONFIRMED','CANCELLED')"
        )
    else:
        op.execute(
            "UPDATE appointments "
            "SET status='CANCELLED', "
            "    cancel_reason=COALESCE(cancel_reason,'MIGRATED_FROM_COMPLETED'), "
            "    hold_expires_at=NULL "
            "WHERE status='COMPLETED'"
        )
        op.execute(
            "UPDATE appointments "
            "SET status='CANCELLED', "
            "    cancel_reason=COALESCE(cancel_reason,'MIGRATED_UNKNOWN_STATUS'), "
            "    hold_expires_at=NULL "
            "WHERE status NOT IN ('HELD','CONFIRMED','CANCELLED')"
        )
    op.execute("UPDATE appointments SET hold_expires_at=NULL WHERE status <> 'HELD' AND hold_expires_at IS NOT NULL")

    if is_postgres:
        op.execute("ALTER TABLE appointments ALTER COLUMN status SET DEFAULT 'CONFIRMED'")
        op.create_check_constraint(
            "chk_appointment_status_axis",
            "appointments",
            "status IN ('HELD','CONFIRMED','CANCELLED')",
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.drop_constraint("chk_appointment_status_axis", "appointments", type_="check")
        op.execute("ALTER TABLE appointments ALTER COLUMN status SET DEFAULT 'SCHEDULED'")
