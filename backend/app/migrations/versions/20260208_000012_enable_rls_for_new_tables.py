"""enable RLS policies for schedule/worker tables

Revision ID: 20260208_000012
Revises: 20260208_000011
Create Date: 2026-02-08 12:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260208_000012"
down_revision = "20260208_000011"
branch_labels = None
depends_on = None


def _has_role(role_name: str) -> bool:
    """Check if a PostgreSQL role exists (Supabase envs have service_role)."""
    from sqlalchemy import text

    conn = op.get_bind()
    result = conn.execute(
        text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role_name}
    ).scalar()
    return result is not None


def upgrade() -> None:
    # Keep consistent with 20260206_000005_enable_rls_policies.py:
    # only Supabase `service_role` (backend API) can access these tables.

    if not _has_role("service_role"):
        # Non-Supabase environment — skip RLS policies (plain PostgreSQL)
        return

    tables = [
        "conversation_locks",
        "project_scheduling",
        "schedule_previews",
        "notification_outbox",
    ]

    for table in tables:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY "{table}_service_role_all" ON public.{table}
            FOR ALL
            TO service_role
            USING (true)
            WITH CHECK (true);
            """
        )


def downgrade() -> None:
    tables = [
        "conversation_locks",
        "project_scheduling",
        "schedule_previews",
        "notification_outbox",
    ]

    for table in tables:
        op.execute(f'DROP POLICY IF EXISTS "{table}_service_role_all" ON public.{table};')
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY;")
