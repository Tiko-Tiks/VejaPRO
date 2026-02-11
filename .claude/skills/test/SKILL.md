---
name: test
description: Run pytest on remote server via SSH. Pass optional test path/pattern as argument.
---

# Remote Test Runner

Run the VejaPRO test suite on the remote server via SSH.

## Usage

- `/test` — run all tests
- `/test test_projects.py` — run a specific test file
- `/test test_projects.py::test_create_project` — run a specific test
- `/test -k "finance"` — run tests matching keyword

## Command

```bash
ssh -i "C:/Users/Administrator/.ssh/vejapro_ed25519" administrator@10.10.50.178 \
  "cd /home/administrator/VejaPRO && \
   DATABASE_URL=sqlite:////tmp/veja_test.db ENVIRONMENT=test PYTHONPATH=backend \
   ENABLE_FINANCE_LEDGER=true ENABLE_MANUAL_PAYMENTS=true ENABLE_EMAIL_INTAKE=true \
   ENABLE_SCHEDULE_ENGINE=true ENABLE_CALENDAR=true \
   SUPABASE_URL=https://fake.supabase.co SUPABASE_KEY=fake TEST_AUTH_ROLE=ADMIN \
   python3 -m pytest backend/tests/$ARGS -v --tb=short \
   --override-ini='filterwarnings='"
```

## Rules

- Replace `$ARGS` with the user's argument. If no argument, leave it empty (runs all tests).
- If user passes just a filename like `test_projects.py`, prepend nothing — the path `backend/tests/test_projects.py` is correct.
- If user passes `-k "something"`, put it after the test path: `backend/tests/ -k "something"`
- Before running, ensure test files are deployed to server if they were recently modified. Use SCP to copy changed files first.
- Report results: total passed, failed, skipped. If failures, show the failure details.

## Fresh DB (if needed)

If tests fail due to schema issues, offer to reset:

```bash
ssh -i "C:/Users/Administrator/.ssh/vejapro_ed25519" administrator@10.10.50.178 \
  "cd /home/administrator/VejaPRO && DATABASE_URL=sqlite:////tmp/veja_test.db \
   PYTHONPATH=backend python3 -c 'from app.core.dependencies import engine; \
   from app.models.project import Base; Base.metadata.drop_all(engine); \
   Base.metadata.create_all(engine)'"
```
