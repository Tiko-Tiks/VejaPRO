---
name: migrate
description: Create a new Alembic migration for VejaPRO
user-invocable: true
disable-model-invocation: true
---

# /migrate — Alembic Migration Generator

Create a new Alembic migration file following VejaPRO conventions.

## Arguments

`/migrate <description>` — short English description of the migration (e.g., "add invoices table")

## Conventions

### File naming

Pattern: `YYYYMMDD_NNNNNN_<snake_case_description>.py`

- Date: today's date
- Sequence: next number after the highest existing `NNNNNN` in `backend/app/migrations/versions/`
- Example: `20260212_000018_add_invoices_table.py`

### Template

```python
"""<description>

Revision ID: YYYYMMDD_NNNNNN
Revises: <previous_revision_id>
Create Date: YYYY-MM-DD

<Extended description if needed>
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "YYYYMMDD_NNNNNN"
down_revision = "<previous_revision_id>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # TODO: implement upgrade
    pass


def downgrade() -> None:
    # TODO: implement downgrade
    pass
```

### Rules

1. **Find the latest migration** by scanning `backend/app/migrations/versions/` for the highest `NNNNNN` sequence number. Use its revision ID as `down_revision`.
2. **Use PostgreSQL dialect types** for production compatibility: `postgresql.UUID(as_uuid=True)`, `postgresql.JSONB`, `sa.DateTime(timezone=True)`.
3. **Server defaults**: Use `sa.text("gen_random_uuid()")` for UUID PKs, `sa.text("now()")` for timestamps.
4. **Always include both** `upgrade()` and `downgrade()`.
5. **Add CHECK constraints** for status/enum columns (pattern: `sa.CheckConstraint("status IN ('A','B','C')", name="chk_<table>_<column>")`).
6. **Add indexes** on foreign key columns and frequently-queried columns.
7. **Write the file** to `backend/app/migrations/versions/`.

### After creating

1. Show the generated file to the user for review.
2. Remind: "Run `/test` to verify the migration applies cleanly against SQLite test DB."
3. Remind: "Deploy to server with `/deploy backend/app/migrations/versions/<filename>`."
