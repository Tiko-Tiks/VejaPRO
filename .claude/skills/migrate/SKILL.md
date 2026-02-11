---
name: migrate
description: Create a new Alembic migration for VejaPRO
user-invocable: true
disable-model-invocation: true
---

# /migrate — Alembic Migration Generator

Create a new Alembic migration file following VejaPRO conventions.

## Arguments

`/migrate <description>` — short English description (e.g., "add invoices table")

## Step 1: Determine sequence

Scan `backend/app/migrations/versions/` for the highest `NNNNNN` sequence number. The new migration gets `NNNNNN + 1`.

Example: if latest is `000017`, new file is `000018`.

## Step 2: Create migration file

### File naming

`YYYYMMDD_NNNNNN_<snake_case_description>.py`

Example: `20260212_000018_add_invoices_table.py`

### Template

```python
"""<description>

Revision ID: YYYYMMDD_NNNNNN
Revises: <previous_revision_id>
Create Date: YYYY-MM-DD
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Only import if needed:
# from sqlalchemy.dialects import postgresql

revision = "YYYYMMDD_NNNNNN"
down_revision = "<previous_revision_id>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Implementation here
    pass


def downgrade() -> None:
    # Reverse of upgrade
    pass
```

## Conventions

### Dual-dialect compatibility (PostgreSQL + SQLite)

Production uses PostgreSQL, tests use SQLite. Migrations must handle both:

- **UUID columns**: Use `sa.String(36)` for SQLite compat, or guard with dialect check:
  ```python
  from sqlalchemy import inspect
  bind = op.get_bind()
  if bind.dialect.name == "sqlite":
      col_type = sa.String(36)
  else:
      col_type = postgresql.UUID(as_uuid=True)
  ```
- **JSONB**: Use `sa.JSON` (works in both). Only use `postgresql.JSONB` if you need JSONB-specific operators.
- **Server defaults**: `sa.text("gen_random_uuid()")` and `sa.text("now()")` are PostgreSQL-only — make them conditional or skip for SQLite.
- **Idempotency**: Use `IF NOT EXISTS` / `IF EXISTS` patterns where possible. Wrap in try/except for SQLite:
  ```python
  try:
      op.create_index(...)
  except Exception:
      pass  # Index already exists (SQLite reruns)
  ```

### Standard patterns

- **CHECK constraints**: `sa.CheckConstraint("status IN ('A','B','C')", name="chk_<table>_<column>")`
- **FK indexes**: Always add indexes on foreign key columns
- **Timestamps**: `sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"))`
- **UUID PKs**: `sa.Column("id", sa.String(36), primary_key=True, server_default=sa.text("gen_random_uuid()"))`
- **Both upgrade + downgrade**: Always implement both directions

### Ruff exemption

Migration files are exempt from ruff linting (configured in `ruff.toml`). Don't worry about import ordering or unused imports in migrations.

## Step 3: Show and guide

1. Show the generated file for review
2. Remind: "Run `/test` to verify the migration applies cleanly"
3. Remind: "Deploy with `/deploy backend/app/migrations/versions/<filename>`"
4. Remind: "After deploy, run Alembic upgrade on server":
   ```bash
   ssh -i "C:/Users/Administrator/.ssh/vejapro_ed25519" administrator@10.10.50.178 \
     "cd /home/administrator/VejaPRO && PYTHONPATH=backend \
      python3 -m alembic -c backend/alembic.ini upgrade head"
   ```
