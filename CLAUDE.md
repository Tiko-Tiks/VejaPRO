# VejaPRO

Lithuanian lawn/garden project management and certification platform.
Forward-only state machine, payments-first doctrine, feature-flag-gated modules.

## Stack

- Python 3.12, FastAPI 0.115, SQLAlchemy 2.0, Alembic, Pydantic 2
- PostgreSQL (Supabase prod) / SQLite (dev/tests)
- External: Stripe, Twilio (SMS/Voice/WhatsApp), Anthropic/OpenAI/Groq, Supabase (auth+storage)
- Lint: ruff 0.15 (`ruff.toml`: Python 3.12, line-length 120, rules E/W/F/I/B/UP, migrations exempt)
- All UI is in Lithuanian (`lang="lt"`)

## Commands

### Lint (local, Windows)

```bash
C:/Users/Administrator/ruff.exe check backend/ --output-format=text
C:/Users/Administrator/ruff.exe format backend/ --check --diff
```

### Tests (run on server via SSH — no local venv pytest)

```bash
# Use inline env vars (production .env has CORS_ALLOW_ORIGINS that breaks pydantic-settings)
ssh -i "C:/Users/Administrator/.ssh/vejapro_ed25519" administrator@10.10.50.178 \
  "cd /home/administrator/VejaPRO && \
   DATABASE_URL=sqlite:////tmp/veja_test.db ENVIRONMENT=test PYTHONPATH=backend \
   ENABLE_FINANCE_LEDGER=true ENABLE_MANUAL_PAYMENTS=true ENABLE_EMAIL_INTAKE=true \
   ENABLE_SCHEDULE_ENGINE=true ENABLE_CALENDAR=true \
   SUPABASE_URL=https://fake.supabase.co SUPABASE_KEY=fake TEST_AUTH_ROLE=ADMIN \
   python3 -m pytest backend/tests -v --tb=short \
   --override-ini='filterwarnings='"
```

Fresh DB before test run (if needed):

```bash
ssh ... "cd /home/administrator/VejaPRO && DATABASE_URL=sqlite:////tmp/veja_test.db \
  PYTHONPATH=backend python3 -c 'from app.core.dependencies import engine; \
  from app.models.project import Base; Base.metadata.drop_all(engine); \
  Base.metadata.create_all(engine)'"
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
    static/         # 17 HTML pages, 1 shared CSS (admin-shared.css), logo
    migrations/     # Alembic (17 applied migrations)
  tests/            # pytest (29 test files, ~298 tests)
  docs/             # Feature documentation
```

### Status state machine

DRAFT -> PAID -> SCHEDULED -> PENDING_EXPERT -> CERTIFIED -> ACTIVE

- Transitions only via `POST /api/v1/transition-status` + `apply_transition()` in `transition_service.py`
- `_is_allowed_actor()` controls RBAC per transition
- PAID requires deposit payment recorded
- ACTIVE requires final payment + client email confirmation

### Feature flags

22 flags in `core/config.py`. Disabled modules return 404 (security: no 403 leak).
Key flags: ENABLE_SCHEDULE_ENGINE, ENABLE_FINANCE_LEDGER, ENABLE_MARKETING_MODULE, ENABLE_TWILIO, ENABLE_EMAIL_INTAKE, ENABLE_AI_CONVERSATION_EXTRACT.

### Admin UI design system (V5.0)

- Single shared CSS: `admin-shared.css` — all 10+ admin pages link to it via `?v=X.X` cache-buster
- Font: DM Sans (Google Fonts, with `opsz` optical sizing)
- Palette: deep obsidian (`#060810`), champagne-amber accent (`#d4a843`), cool sapphire info (`#6ba3f7`)
- Design tokens in `:root` — always use CSS variables, never hardcode colors
- All admin pages share: sidebar (248px), hamburger mobile toggle, `.admin-layout` grid
- When bumping design version: update `?v=` param in ALL admin HTML `<link>` tags

### Payments-first doctrine

Status cannot advance without payment facts. Deposit -> PAID, Final payment -> eligible for ACTIVE.
Finance ledger tracks all payments (V2.3).

## Key gotchas

- **CSS cache-busting across admin pages**: `admin-shared.css?v=5.0` — when changing CSS, bump `?v=` in ALL 10+ admin HTML files or users see stale styles.
- **Server .env in `backend/`**: Production `.env` is at `backend/.env` (not project root). It has `CORS_ALLOW_ORIGINS` that breaks pydantic-settings JSON parsing — always use inline env vars for running tests.
- **`POST /projects` returns flat JSON**: Response is `{id, status, ...}` directly — NOT wrapped in `{"project": {...}}`. But `GET /projects/{id}` DOES wrap: `{"project": {...}}`.
- **Finance endpoint URL has no `/finance/` prefix**: All routers mounted at `/api/v1`, so quick-payment is `/api/v1/projects/{id}/quick-payment-and-transition` (not `/api/v1/finance/...`).
- **SQLite naive datetimes**: Tests use SQLite which returns naive datetimes. Always `.replace(tzinfo=None)` for comparisons.
- **`test_marketing_flags.py` cleanup**: This test clears `app.dependency_overrides` — conftest must re-check/re-apply overrides.
- **`provider_event_id` uniqueness**: Use `uuid.uuid4()` in tests to avoid stale data conflicts.
- **conftest.py auth**: Uses `X-Test-Role` / `X-Test-Sub` / `X-Test-Email` headers + dependency override when `SUPABASE_JWT_SECRET` is absent.
- **Client confirmation chicken-and-egg**: Must `create_client_confirmation()` and flush BEFORE `apply_transition(ACTIVE)` because `is_client_confirmed()` checks DB.
- **Auto-deploy**: systemd timer polls `origin/main` every 5 min — pushed code goes live automatically.
- **PII policy**: Admin UI never shows raw email/phone. Uses `maskEmail()`, `maskPhone()` helpers.
- **`gh` CLI not installed**: Use PowerShell + GitHub REST API for PR creation on this Windows machine.
- **Worktree cleanup on Windows**: `git worktree remove` fails with "Directory not empty" — use `git worktree prune` after deleting dirs.

## Claude Code tools

### Skills (invoke with `/name`)

- `/test [args]` — run pytest on remote server via SSH (`/test`, `/test test_projects.py`, `/test -k "finance"`)
- `/deploy <files>` — deploy files to server via SCP+SSH (user-only, asks confirmation)
- `/migrate <description>` — generate new Alembic migration

### Agents (subagents for review tasks)

- `security-reviewer` — audits PII exposure, auth bypass, RBAC, feature flag leaks
- `migration-reviewer` — reviews Alembic migrations for safety and backwards-compat

### Hooks (automatic)

- **PostToolUse**: `ruff check --fix` + `ruff format` on every `.py` file edit
- **PreToolUse**: blocks edits to `.env`, locked specs (`KONSTITUCIJA`, `SCHEDULE_ENGINE_V1_SPEC`), applied Alembic migrations

## Conventions

- Commit messages: English, conventional-commit-ish (`feat:`, `fix:`, `docs:`, `test:`)
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
