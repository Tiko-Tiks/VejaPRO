"""schedule engine phase 0 foundations

Revision ID: 20260207_000007
Revises: 20260206_000006
Create Date: 2026-02-07 13:20:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260207_000007"
down_revision = "20260206_000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.add_column(
        "appointments",
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "appointments",
        sa.Column(
            "visit_type",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'PRIMARY'"),
        ),
    )
    op.add_column(
        "appointments",
        sa.Column(
            "lock_level", sa.SmallInteger(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column(
        "appointments",
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "appointments",
        sa.Column("locked_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("appointments", sa.Column("lock_reason", sa.Text(), nullable=True))
    op.add_column(
        "appointments",
        sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "appointments",
        sa.Column(
            "weather_class",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'MIXED'"),
        ),
    )
    op.add_column("appointments", sa.Column("route_date", sa.Date(), nullable=True))
    op.add_column(
        "appointments", sa.Column("route_sequence", sa.Integer(), nullable=True)
    )
    op.add_column(
        "appointments",
        sa.Column(
            "row_version", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
    )
    op.add_column(
        "appointments",
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "appointments",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "appointments",
        sa.Column("cancelled_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("appointments", sa.Column("cancel_reason", sa.Text(), nullable=True))

    op.create_foreign_key(
        "fk_appointments_resource_id",
        "appointments",
        "users",
        ["resource_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_appointments_locked_by",
        "appointments",
        "users",
        ["locked_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_appointments_superseded_by",
        "appointments",
        "appointments",
        ["superseded_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_appointments_cancelled_by",
        "appointments",
        "users",
        ["cancelled_by"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_check_constraint(
        "chk_appt_link",
        "appointments",
        "(project_id IS NOT NULL OR call_request_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "chk_hold_only_when_held",
        "appointments",
        "((status = 'HELD' AND hold_expires_at IS NOT NULL) OR (status <> 'HELD' AND hold_expires_at IS NULL))",
    )

    op.create_index(
        "idx_appt_resource_time",
        "appointments",
        ["resource_id", "starts_at"],
        unique=False,
    )
    op.create_index(
        "idx_appt_project_time",
        "appointments",
        ["project_id", "starts_at"],
        unique=False,
    )
    op.create_index(
        "idx_appt_route",
        "appointments",
        ["route_date", "resource_id", "route_sequence"],
        unique=False,
    )
    if is_postgres:
        op.create_index(
            "idx_appt_hold_exp",
            "appointments",
            ["hold_expires_at"],
            unique=False,
            postgresql_where=sa.text("status='HELD'"),
        )
        op.create_index(
            "uniq_project_confirmed_visit",
            "appointments",
            ["project_id", "visit_type"],
            unique=True,
            postgresql_where=sa.text("status='CONFIRMED' AND project_id IS NOT NULL"),
        )
        op.execute(
            """
            ALTER TABLE appointments
            ADD CONSTRAINT no_overlap_per_resource
            EXCLUDE USING gist (
                resource_id WITH =,
                tstzrange(starts_at, ends_at, '[)') WITH &&
            )
            WHERE (status IN ('HELD','CONFIRMED'))
            """
        )
    else:
        op.create_index(
            "idx_appt_hold_exp", "appointments", ["hold_expires_at"], unique=False
        )

    op.create_table(
        "conversation_locks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("conversation_id", sa.String(length=128), nullable=False),
        sa.Column(
            "appointment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("appointments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "visit_type",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'PRIMARY'"),
        ),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "channel", "conversation_id", name="uniq_conversation_lock"
        ),
    )
    op.create_index("idx_conv_lock_exp", "conversation_locks", ["hold_expires_at"])
    op.create_index(
        "idx_conv_lock_visit", "conversation_locks", ["appointment_id", "visit_type"]
    )

    op.create_table(
        "project_scheduling",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "ready_to_schedule",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "default_weather_class",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'MIXED'"),
        ),
        sa.Column("estimated_duration_min", sa.Integer(), nullable=False),
        sa.Column(
            "priority_score", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("preferred_time_windows", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_sched_ready", "project_scheduling", ["ready_to_schedule", "priority_score"]
    )

    op.create_table(
        "schedule_previews",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("route_date", sa.Date(), nullable=False),
        sa.Column(
            "resource_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("preview_hash", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_schedule_preview_exp", "schedule_previews", ["expires_at"])
    op.create_index(
        "idx_schedule_preview_route_resource",
        "schedule_previews",
        ["route_date", "resource_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.drop_index("idx_schedule_preview_route_resource", table_name="schedule_previews")
    op.drop_index("idx_schedule_preview_exp", table_name="schedule_previews")
    op.drop_table("schedule_previews")

    op.drop_index("idx_sched_ready", table_name="project_scheduling")
    op.drop_table("project_scheduling")

    op.drop_index("idx_conv_lock_visit", table_name="conversation_locks")
    op.drop_index("idx_conv_lock_exp", table_name="conversation_locks")
    op.drop_table("conversation_locks")

    if is_postgres:
        op.execute(
            "ALTER TABLE appointments DROP CONSTRAINT IF EXISTS no_overlap_per_resource"
        )
        op.drop_index("uniq_project_confirmed_visit", table_name="appointments")
    op.drop_index("idx_appt_hold_exp", table_name="appointments")
    op.drop_index("idx_appt_route", table_name="appointments")
    op.drop_index("idx_appt_project_time", table_name="appointments")
    op.drop_index("idx_appt_resource_time", table_name="appointments")

    op.drop_constraint("chk_hold_only_when_held", "appointments", type_="check")
    op.drop_constraint("chk_appt_link", "appointments", type_="check")
    op.drop_constraint(
        "fk_appointments_cancelled_by", "appointments", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_appointments_superseded_by", "appointments", type_="foreignkey"
    )
    op.drop_constraint("fk_appointments_locked_by", "appointments", type_="foreignkey")
    op.drop_constraint(
        "fk_appointments_resource_id", "appointments", type_="foreignkey"
    )

    op.drop_column("appointments", "cancel_reason")
    op.drop_column("appointments", "cancelled_by")
    op.drop_column("appointments", "cancelled_at")
    op.drop_column("appointments", "superseded_by_id")
    op.drop_column("appointments", "row_version")
    op.drop_column("appointments", "route_sequence")
    op.drop_column("appointments", "route_date")
    op.drop_column("appointments", "weather_class")
    op.drop_column("appointments", "hold_expires_at")
    op.drop_column("appointments", "lock_reason")
    op.drop_column("appointments", "locked_by")
    op.drop_column("appointments", "locked_at")
    op.drop_column("appointments", "lock_level")
    op.drop_column("appointments", "visit_type")
    op.drop_column("appointments", "resource_id")
