---
name: test
description: Run pytest on remote server via SSH. Pass optional test path/pattern as argument.
---

# Remote Test Runner

Run the VejaPRO test suite on the remote server via SSH.

## Usage

- `/test` — run all tests
- `/test test_projects.py` — run a specific file (root-level)
- `/test api/test_projects.py` — run a specific file (api/ subdirectory)
- `/test test_projects.py::test_create_project` — run a specific test function
- `/test -k "finance"` — run tests matching keyword
- `/test --fresh` — reset DB then run all tests

## Test directory structure

```
backend/tests/
  test_*.py              # 23 root-level test files
  api/test_*.py          # 6 API integration test files
  conftest.py            # Shared fixtures, auth override
```

## Step 1: Sync modified files to server

Before running tests, check if any Python files were modified locally. If so, deploy them first:

```bash
# For each modified .py file:
scp -i "/home/vejaserv/.ssh/vejapro_ed25519" "<local-path>" administrator@10.10.50.178:/tmp/<filename>
ssh -i "/home/vejaserv/.ssh/vejapro_ed25519" administrator@10.10.50.178 \
  "rm /home/administrator/VejaPRO/<path> 2>/dev/null; cp /tmp/<filename> /home/administrator/VejaPRO/<path>"
```

Use `git diff --name-only HEAD` or `git status --porcelain` to find modified files. Only sync `.py` files under `backend/`.

## Step 2: Run tests

```bash
ssh -i "/home/vejaserv/.ssh/vejapro_ed25519" administrator@10.10.50.178 \
  "cd /home/administrator/VejaPRO && \
   DATABASE_URL=sqlite:////tmp/veja_test.db ENVIRONMENT=test PYTHONPATH=backend \
   ENABLE_FINANCE_LEDGER=true ENABLE_MANUAL_PAYMENTS=true ENABLE_EMAIL_INTAKE=true \
   ENABLE_SCHEDULE_ENGINE=true ENABLE_CALENDAR=true \
   SUPABASE_URL=https://fake.supabase.co SUPABASE_KEY=fake TEST_AUTH_ROLE=ADMIN \
   python3 -m pytest backend/tests/{ARGS} -v --tb=short \
   --override-ini='filterwarnings='"
```

### Argument mapping

| User input | `{ARGS}` value |
|---|---|
| (empty) | (empty — runs all) |
| `test_projects.py` | `test_projects.py` |
| `api/test_projects.py` | `api/test_projects.py` |
| `test_projects.py::test_create_project` | `test_projects.py::test_create_project` |
| `-k "finance"` | `-k "finance"` (append after path) |
| `--fresh` | Reset DB first (see below), then run all |

For failures, re-run the failing test with `--tb=long` for full traceback.

## Step 3: Report results

Summarize: **X passed, Y failed, Z skipped** (duration).
If failures: show the failure output. If flaky (passes alone, fails in suite): note as flaky.

## Fresh DB reset

Use when tests fail due to schema drift or stale data:

```bash
ssh -i "/home/vejaserv/.ssh/vejapro_ed25519" administrator@10.10.50.178 \
  "cd /home/administrator/VejaPRO && DATABASE_URL=sqlite:////tmp/veja_test.db \
   PYTHONPATH=backend python3 -c 'from app.core.dependencies import engine; \
   from app.models.project import Base; Base.metadata.drop_all(engine); \
   Base.metadata.create_all(engine); print(\"DB reset OK\")'"
```

## Known issues

- `test_marketing_flags.py` clears `app.dependency_overrides` — may affect subsequent tests
- Schedule engine tests are sensitive to stale Appointment data — use `--fresh` if they fail
- 4 token endpoint tests skip when `SUPABASE_JWT_SECRET` is missing (expected)
