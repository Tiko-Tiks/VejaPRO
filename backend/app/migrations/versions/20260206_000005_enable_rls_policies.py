"""enable RLS policies for all tables

Revision ID: 20260206_000005
Revises: 20260206_000004
Create Date: 2026-02-06 13:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260206_000005"
down_revision = "20260206_000004"
branch_labels = None
depends_on = None


def _has_role(role_name: str) -> bool:
    """Check if a PostgreSQL role exists (Supabase envs have service_role)."""
    from sqlalchemy import text

    conn = op.get_bind()
    result = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role_name}).scalar()
    return result is not None


def upgrade() -> None:
    # Enable RLS on all public tables (except alembic_version which is internal)
    # VejaPRO uses backend API for all access, so we disable public access via RLS
    # Only service_role (backend) can access tables

    if not _has_role("service_role"):
        # Non-Supabase environment — skip RLS policies (plain PostgreSQL)
        return

    tables = [
        "users",
        "margins",
        "projects",
        "audit_logs",
        "payments",
        "sms_confirmations",
        "evidences",
        "appointments",
        "call_requests",
    ]

    for table in tables:
        # Enable RLS
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;")

        # Create policy: only service_role can access (backend API)
        # This blocks direct PostgREST access from anon/authenticated users
        op.execute(
            f"""
            CREATE POLICY "{table}_service_role_all" ON public.{table}
            FOR ALL
            TO service_role
            USING (true)
            WITH CHECK (true);
            """
        )

    # alembic_version doesn't need RLS (it's internal migration tracking)
    # We'll enable it anyway to satisfy the linter
    op.execute("ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY "alembic_version_service_role_all" ON public.alembic_version
        FOR ALL
        TO service_role
        USING (true)
        WITH CHECK (true);
        """
    )


def downgrade() -> None:
    tables = [
        "users",
        "margins",
        "projects",
        "audit_logs",
        "payments",
        "sms_confirmations",
        "evidences",
        "appointments",
        "call_requests",
        "alembic_version",
    ]

    for table in tables:
        op.execute(f'DROP POLICY IF EXISTS "{table}_service_role_all" ON public.{table};')
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY;")
