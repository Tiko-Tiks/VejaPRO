# VejaPRO

Lithuanian lawn/garden project management and certification platform.
Forward-only state machine, payments-first doctrine, feature-flag-gated modules.

## Stack

- Python 3.12 target (CI/lint), FastAPI 0.115, SQLAlchemy 2.0, Alembic, Pydantic 2
- Production runtime: Python 3.13.3 (Ubuntu VM venv)
- PostgreSQL (Supabase prod) / SQLite (dev/tests)
- External: Stripe, Twilio (SMS/Voice/WhatsApp), Anthropic/OpenAI/Groq, Supabase (auth+storage)
- Lint: ruff 0.15 (`ruff.toml`: Python 3.12, line-length 120, rules E/W/F/I/B/UP, migrations exempt)
- All UI is in Lithuanian (`lang="lt"`)

## Commands

### Lint (local, Windows)

```bash
C:/Users/Administrator/ruff.exe check backend/
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

All feature flags enabled in CI except ENABLE_STRIPE, ENABLE_VISION_AI, ENABLE_AI_FINANCE_EXTRACT, ENABLE_AI_OVERRIDES, ENABLE_AI_VISION. Email webhook/sentiment/auto-reply enabled (tests mock internally).

#### Debugging CI failures

```bash
# Get GitHub token and fetch recent runs (use Windows paths, not /tmp/)
TOKEN=$(echo "protocol=https\nhost=github.com" | git credential fill | grep "^password" | cut -d= -f2)
curl -s -H "Authorization: token $TOKEN" \
  "https://api.github.com/repos/Tiko-Tiks/VejaPRO/actions/runs?per_page=5" \
  -o "C:/Users/Administrator/Desktop/runs.json"
# Get job logs (follow redirect with -L)
curl -sL -H "Authorization: token $TOKEN" \
  "https://api.github.com/repos/Tiko-Tiks/VejaPRO/actions/jobs/{JOB_ID}/logs" \
  -o "C:/Users/Administrator/Desktop/log.txt"
```

Note: `gh` CLI not installed — use `curl` + `git credential fill` for GitHub API.

## Architecture

### Directory layout

```
backend/
  app/
    api/v1/         # Route files (projects.py, finance.py, schedule.py, email_webhook.py, ...)
    core/           # Config, dependencies, auth, storage, image_processing
    models/         # SQLAlchemy models (project.py is the main one)
    schemas/        # Pydantic schemas
    services/       # Business logic (transition_service.py, admin_read_models.py, ...)
      ai/           # AI services: intent/, conversation_extract/, sentiment/
    static/         # 17 HTML pages, 1 shared CSS (admin-shared.css), logo
    migrations/     # Alembic (17 applied migrations)
  tests/            # pytest (30 test files, ~374 tests)
  docs/             # Feature documentation
```

### Status state machine

DRAFT -> PAID -> SCHEDULED -> PENDING_EXPERT -> CERTIFIED -> ACTIVE

- Transitions only via `POST /api/v1/transition-status` + `apply_transition()` in `transition_service.py`
- `_is_allowed_actor()` controls RBAC per transition
- PAID requires deposit payment recorded
- ACTIVE requires final payment + client email confirmation

### Feature flags

26 flags in `core/config.py`. Disabled modules return 404 (security: no 403 leak).
Key flags: ENABLE_SCHEDULE_ENGINE, ENABLE_FINANCE_LEDGER, ENABLE_MARKETING_MODULE, ENABLE_TWILIO, ENABLE_EMAIL_INTAKE, ENABLE_AI_CONVERSATION_EXTRACT, ENABLE_EMAIL_WEBHOOK, ENABLE_AI_EMAIL_SENTIMENT, ENABLE_EMAIL_AUTO_REPLY.

### Admin UI design system (V5.1)

- Single shared CSS: `admin-shared.css` — all 10+ admin pages link to it via `?v=X.X` cache-buster
- Design tokens in `:root` — always use CSS variables, never hardcode colors
- When bumping design version: update `?v=` param in ALL admin HTML `<link>` tags

### Payments-first doctrine

Status cannot advance without payment facts. Deposit -> PAID, Final payment -> eligible for ACTIVE.
Finance ledger tracks all payments (V2.3).

### AI service architecture

AI services follow scope-based routing: `router.resolve("scope")` -> `ResolvedConfig(provider, model, timeout)`.
- Add new scope: config.py (flags) -> router.py (3 insertion points) -> audit.py (SCOPE_ACTIONS) -> service module
- Existing scopes: `intent`, `conversation_extract`, `sentiment`
- Services live in `app/services/ai/{scope}/` with `__init__.py`, `contracts.py`, `service.py`
- Audit on success only — failure via `logger.warning()` (noise control for webhook retries)

## Key gotchas

- **CI requires all code committed**: Tests referencing new config fields/functions will fail if source files aren't committed. Always `git diff --name-only HEAD` before pushing.
- **New feature flags need CI env vars**: When adding flags to `config.py`, also add to `.github/workflows/ci.yml` env section.
- **Lazy imports break mock targets**: Twilio `Client` is lazy-imported inside functions. Mock at source (`twilio.rest.Client`) not at usage (`app.services.module.Client`).
- **CloudMailin dev mode**: Email webhook allows unauthenticated requests when `CLOUDMAILIN_USERNAME`/`CLOUDMAILIN_PASSWORD` are empty. Don't add mandatory credential checks.
- **Server .env in `backend/`**: Production `.env` is at `backend/.env`. `CORS_ALLOW_ORIGINS` breaks pydantic-settings — always use inline env vars for tests.
- **SQLite naive datetimes**: Tests use SQLite which returns naive datetimes. Always `.replace(tzinfo=None)` for comparisons.
- **`test_marketing_flags.py` cleanup**: This test clears `app.dependency_overrides` — conftest must re-check/re-apply overrides.
- **`provider_event_id` uniqueness**: Use `uuid.uuid4()` in tests to avoid stale data conflicts.
- **conftest.py auth**: Uses `X-Test-Role` / `X-Test-Sub` / `X-Test-Email` headers + dependency override when `SUPABASE_JWT_SECRET` is absent.
- **Client confirmation chicken-and-egg**: Must `create_client_confirmation()` and flush BEFORE `apply_transition(ACTIVE)`.
- **Auto-deploy**: systemd timer polls `origin/main` every 5 min — pushed code goes live automatically.
- **PII policy**: Admin UI never shows raw email/phone. Uses `maskEmail()`, `maskPhone()` helpers.
- **Forwarded IP headers gated**: `X-Real-IP` / `X-Forwarded-For` trusted only when peer is in `TRUSTED_PROXY_CIDRS`.
- **`/api/v1/admin/token` requires secret header**: `ADMIN_TOKEN_ENDPOINT_ENABLED=true` + `ADMIN_TOKEN_ENDPOINT_SECRET`; callers must send `X-Admin-Token-Secret`.
- **`python3` not in Git Bash**: Use `python` (not `python3`) for local scripting. Server SSH uses `python3`.
- **intake_state JSONB merge**: Always `state = dict(cr.intake_state or {}); state["key"] = ...; cr.intake_state = state; db.add(cr)`. Never overwrite entire JSONB.
- **CSS cache-busting**: `admin-shared.css?v=5.1` — bump `?v=` in ALL admin HTML `<link>` and `<script>` tags when changing shared CSS/JS.

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

## GitHub branch protection (`main`)

- **Direct push to `main` is blocked** — always use a PR (even for single-line fixes)
- **CI must pass** (`tests` job) before merge is allowed
- **Strict status checks** — PR branch must be up-to-date with `main`
- **Enforce admins** — these rules apply to everyone, including repo owner
- **Linear history required** — squash merge only, no merge commits
- **Force push and branch deletion forbidden** on `main`
- After merge: delete the feature branch (remote + local)

## Conventions

- Commit messages: English, conventional-commit-ish (`feat:`, `fix:`, `docs:`, `test:`)
- All documentation files: Lithuanian (except this file and commit messages)
- No direct status updates — always workflow transitions
- 404 for disabled features (not 403)
- Actor types: CLIENT, SUBCONTRACTOR, EXPERT, ADMIN, SYSTEM_STRIPE, SYSTEM_TWILIO, SYSTEM_EMAIL
- **Never push directly to `main`** — always branch + PR + CI green + squash merge

### Documentation update checklist (new features)

1. `STATUS.md` — version bump, metrics, module table row
2. `backend/VEJAPRO_TECHNINE_DOKUMENTACIJA_V2.md` — feature flags list, new section
3. `backend/API_ENDPOINTS_CATALOG.md` — feature flags list, new endpoint section
4. `backend/.env.example` — new env vars with comments
5. `CLAUDE.md` — flag count, test count, key flags list

## Documentation index

- `STATUS.md` — live project status, version, module table
- `INFRASTRUCTURE.md` — deploy runbook, rollback, troubleshooting
- `CONTRIBUTING.md` — developer workflow, PR process, conventions
- `backend/VEJAPRO_KONSTITUCIJA_V2.md` — business rules (LOCKED)
- `backend/VEJAPRO_TECHNINE_DOKUMENTACIJA_V2.md` — technical spec
- `backend/API_ENDPOINTS_CATALOG.md` — all 79+ endpoints
- `backend/docs/ADMIN_UI_V3.md` — admin UI architecture
- `backend/SCHEDULE_ENGINE_V1_SPEC.md` — schedule engine spec (LOCKED)
- `backend/GALLERY_DOCUMENTATION.md` — gallery feature
