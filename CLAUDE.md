# VejaPRO

Lithuanian lawn/garden project management and certification platform.
Forward-only state machine, payments-first doctrine, feature-flag-gated modules.

## Stack

- Python 3.12, FastAPI 0.115, SQLAlchemy 2.0, Alembic, Pydantic 2
- PostgreSQL (Supabase prod) / SQLite (dev/tests)
- External: Stripe, Twilio (SMS/Voice/WhatsApp), Anthropic/OpenAI/Groq, Supabase (auth+storage)
- Lint: ruff 0.15
- All UI is in Lithuanian (`lang="lt"`)

## Commands

### Lint (local, Windows)

```bash
C:/Users/Administrator/ruff.exe check backend/ --output-format=text
C:/Users/Administrator/ruff.exe format backend/ --check --diff
```

### Tests (run on server via SSH — no local venv pytest)

```bash
ssh -i "C:/Users/Administrator/.ssh/vejapro_ed25519" administrator@10.10.50.178 \
  "cd /home/administrator/VejaPRO && set -a && . ./.env && set +a && \
   PYTHONPATH=backend python3 -m pytest backend/tests -v --tb=short \
   --override-ini='filterwarnings='"
```

### Deploy files to server

```bash
scp -i "C:/Users/Administrator/.ssh/vejapro_ed25519" <local-file> \
  administrator@10.10.50.178:/tmp/<filename>
ssh -i "C:/Users/Administrator/.ssh/vejapro_ed25519" administrator@10.10.50.178 \
  "rm /home/administrator/VejaPRO/<path> && cp /tmp/<filename> /home/administrator/VejaPRO/<path>"
```

Root-owned files: `rm` then `cp` from `/tmp/` (no sudo password available).

### CI (GitHub Actions)

```
ruff check -> ruff format --check -> pytest (SQLite, PYTHONPATH=backend)
```

All feature flags enabled in CI except ENABLE_STRIPE, ENABLE_VISION_AI, ENABLE_AI_FINANCE_EXTRACT, ENABLE_AI_OVERRIDES, ENABLE_AI_VISION.

## Architecture

### Directory layout

```
backend/
  app/
    api/v1/         # Route files (projects.py, finance.py, schedule.py, ...)
    core/           # Config, dependencies, auth, storage, image_processing
    models/         # SQLAlchemy models (project.py is the main one)
    schemas/        # Pydantic schemas
    services/       # Business logic (transition_service.py, admin_read_models.py, ...)
    static/         # All HTML pages (17 files), CSS, JS
    migrations/     # Alembic (16 applied migrations)
  tests/            # pytest (28 test files, ~280 tests)
  docs/             # Feature documentation
```

### Status state machine

DRAFT -> PAID -> SCHEDULED -> PENDING_EXPERT -> CERTIFIED -> ACTIVE

- Transitions only via `POST /api/v1/transition-status` + `apply_transition()` in `transition_service.py`
- `_is_allowed_actor()` controls RBAC per transition
- PAID requires deposit payment recorded
- ACTIVE requires final payment + client email confirmation

### Feature flags

20 flags in `core/config.py`. Disabled modules return 404 (security: no 403 leak).
Key flags: ENABLE_SCHEDULE_ENGINE, ENABLE_FINANCE_LEDGER, ENABLE_MARKETING_MODULE, ENABLE_TWILIO, ENABLE_EMAIL_INTAKE.

### Payments-first doctrine

Status cannot advance without payment facts. Deposit -> PAID, Final payment -> eligible for ACTIVE.
Finance ledger tracks all payments (V2.3).

## Key gotchas

- **SQLite naive datetimes**: Tests use SQLite which returns naive datetimes. Always `.replace(tzinfo=None)` for comparisons.
- **`test_marketing_flags.py` cleanup**: This test clears `app.dependency_overrides` — conftest must re-check/re-apply overrides.
- **`provider_event_id` uniqueness**: Use `uuid.uuid4()` in tests to avoid stale data conflicts.
- **Server .env is minimal**: Only `DATABASE_URL` — no JWT secret, no feature flags. Tests skip gracefully when features missing.
- **conftest.py auth**: Uses `X-Test-Role` / `X-Test-User-Id` headers + dependency override when `SUPABASE_JWT_SECRET` is absent.
- **Client confirmation chicken-and-egg**: Must `create_client_confirmation()` and flush BEFORE `apply_transition(ACTIVE)` because `is_client_confirmed()` checks DB.
- **Auto-deploy**: systemd timer polls `origin/main` every 5 min — pushed code goes live automatically.
- **PII policy**: Admin UI never shows raw email/phone. Uses `maskEmail()`, `maskPhone()` helpers.

## Conventions

- Commit messages: English, conventional-commit-ish (`feat:`, `fix:`, `docs:`, `style:`)
- All documentation files: Lithuanian (except this file and commit messages)
- No direct status updates — always workflow transitions
- 404 for disabled features (not 403)
- Actor types: CLIENT, SUBCONTRACTOR, EXPERT, ADMIN, SYSTEM_STRIPE, SYSTEM_TWILIO, SYSTEM_EMAIL

## Documentation index

- `STATUS.md` — live project status, version, module table
- `INFRASTRUCTURE.md` — deploy runbook
- `backend/VEJAPRO_KONSTITUCIJA_V2.md` — business rules (LOCKED)
- `backend/VEJAPRO_TECHNINE_DOKUMENTACIJA_V2.md` — technical spec
- `backend/API_ENDPOINTS_CATALOG.md` — all 78+ endpoints
- `backend/docs/ADMIN_UI_V3.md` — admin UI architecture
- `backend/SCHEDULE_ENGINE_V1_SPEC.md` — schedule engine spec (LOCKED)
- `backend/GALLERY_DOCUMENTATION.md` — gallery feature
