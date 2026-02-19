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

All feature flags enabled in CI except ENABLE_STRIPE, ENABLE_VISION_AI, ENABLE_AI_FINANCE_EXTRACT, ENABLE_AI_OVERRIDES, ENABLE_AI_VISION. Email webhook/sentiment/auto-reply and AI pricing enabled (tests mock internally).

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
    services/       # Business logic (transition_service.py, admin_read_models.py, email_templates.py, ...)
      ai/           # AI services: intent/, conversation_extract/, sentiment/, pricing/
    static/         # 23 HTML pages, 10 JS modules, 3 CSS files, logo
    migrations/     # Alembic (17 applied migrations)
  tests/            # pytest (35 test files)
  docs/             # Feature documentation
```

### Status state machine

DRAFT -> PAID -> SCHEDULED -> PENDING_EXPERT -> CERTIFIED -> ACTIVE

- Transitions only via `POST /api/v1/transition-status` + `apply_transition()` in `transition_service.py`
- `_is_allowed_actor()` controls RBAC per transition
- PAID requires deposit payment recorded
- ACTIVE requires final payment + client email confirmation

### Feature flags

28 flags in `core/config.py`. Disabled modules return 404 (security: no 403 leak).
Key flags: ENABLE_SCHEDULE_ENGINE, ENABLE_FINANCE_LEDGER, ENABLE_MARKETING_MODULE, ENABLE_TWILIO, ENABLE_EMAIL_INTAKE, ENABLE_AI_CONVERSATION_EXTRACT, ENABLE_EMAIL_WEBHOOK, ENABLE_AI_EMAIL_SENTIMENT, ENABLE_EMAIL_AUTO_REPLY, ENABLE_ADMIN_OPS_V1, ENABLE_AI_PRICING.

### Admin UI design system (V6.0)

- Single shared CSS: `admin-shared.css` — all 15 admin pages link to it via `?v=6.5` cache-buster
- 10 JS modules: `admin-shared.js`, `admin-planner.js`, `admin-projects.js`, `admin-project-day.js`, `admin-client-card.js`, `admin-archive.js`, `gallery-dynamic.js`, `login.js`, `public-shared.js`, `register.js`
- **Light/dark theme**: `Theme` object in `admin-shared.js`, toggle button in sidebar, `localStorage["vejapro_theme"]`
- FOUC prevention: inline `<script>` in `<head>` of every admin HTML reads localStorage before first paint
- CSS structure: `:root` (shared tokens) + `:root, [data-theme="light"]` (light) + `[data-theme="dark"]` (dark)
- Sidebar always dark (`--sidebar-bg: #1a1a2e`) in both themes
- Dashboard: planner (Ops V1) or legacy work queue depending on `ENABLE_ADMIN_OPS_V1`
- Bare form elements auto-styled in admin containers (no `.form-input` class needed)
- Design tokens — always use CSS variables, never hardcode colors
- When bumping design version: update `?v=` param in ALL admin HTML `<link>` and `<script>` tags

### Public design system (V1.0)

- Separate from admin: `public-shared.css` (1012 lines) + `public-shared.js` (215 lines)
- Green/gold palette: `--vp-green-*`, `--vp-gold-*` CSS custom properties
- Pages using it: `landing.html`, `gallery.html`, `login.html` (dual-mode), `register.html`
- Components: sticky header, hamburger menu, hero, card grid, process timeline, pricing cards, lead form, footer, mobile sticky bar
- Before/after lightbox: `window.VPLightbox` in `public-shared.js`
- Responsive: mobile-first with 768px / 480px breakpoints
- Cache-busting: `?v=1.0` on `<link>` and `<script>` tags

### Admin Ops V1 (planner, inbox, client card, archive)

Flag: `ENABLE_ADMIN_OPS_V1`. When enabled, `/admin` serves planner; when disabled, serves legacy dashboard.

**Pages:**
- `admin.html` + `admin-planner.js` — monthly calendar planner + inbox (needs-human tasks)
- `admin-project-day.html` + `admin-project-day.js` — single-project day view (checklist, evidence upload, day actions)
- `admin-client-card.html` + `admin-client-card.js` — unified client card with AI pricing workflow (generate/approve/edit/ignore + survey)
- `admin-archive.html` + `admin-archive.js` — search/filter all clients+projects (client-side filtering)
- `admin-legacy.html` — fallback dashboard when Ops V1 disabled

**Endpoints** (`backend/app/api/v1/admin_ops.py`):
- `GET /api/v1/admin/ops/day/{date}/plan` — day plan with appointments + project details
- `GET /api/v1/admin/ops/inbox` — needs-human inbox (attention projects, HELD appointments, NEW calls)
- `POST /api/v1/admin/ops/project/{id}/day-action` — record day actions (check_in, complete, upload_photo)
- `GET /api/v1/admin/ops/client/{client_key}/card` — comprehensive client card with AI pricing payload (`pricing_project_id`, `ai_pricing`, `ai_pricing_meta`, `ai_pricing_decision`, `extended_survey`)
- `POST /api/v1/admin/ops/client/{client_key}/proposal-action` — record proposal decisions
- `POST /api/v1/admin/pricing/{project_id}/generate` — generate AI pricing proposal (`ok|fallback`)
- `POST /api/v1/admin/pricing/{project_id}/decide` — human decision (approve/edit/ignore) with fingerprint stale guard + decision hard-gate
- `PUT /api/v1/admin/pricing/{project_id}/survey` — save extended site survey for pricing

**Inbox dedup:** task_id = hash(client_key + entity_type + entity_id + task_type + version_key). Sorted by priority then updated_at.

### Payments-first doctrine

Status cannot advance without payment facts. Deposit -> PAID, Final payment -> eligible for ACTIVE.
Finance ledger tracks all payments (V2.3).

### AI service architecture

AI services follow scope-based routing: `router.resolve("scope")` -> `ResolvedConfig(provider, model, timeout)`.
- Add new scope: config.py (flags) -> router.py (3 insertion points) -> audit.py (SCOPE_ACTIONS) -> service module
- Existing scopes: `intent`, `conversation_extract`, `sentiment`, `pricing`
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
- **CSS cache-busting**: `admin-shared.css?v=6.5` — bump `?v=` in ALL admin HTML `<link>` and `<script>` tags when changing shared CSS/JS.
- **Theme system**: Light/dark toggle via `Theme.toggle()` in `admin-shared.js`. FOUC prevention script must exist in `<head>` of every admin HTML. CSS variables split: `:root` (shared), `:root,[data-theme="light"]` (light), `[data-theme="dark"]` (dark).
- **Ops V1 dual dashboard**: `admin.html` (planner) vs `admin-legacy.html` — gated by `ENABLE_ADMIN_OPS_V1`. New pages use `data-layout="topbar"` attribute.
- **ES256 + HS256 dual auth**: `auth.py` verifies both HS256 (via `SUPABASE_JWT_SECRET`) and ES256 (via JWKS from `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`). Peeks at token header `alg` to choose strategy order.
- **`SUPABASE_ANON_KEY`**: Legacy JWT anon key (eyJ...) for Supabase Auth API. Falls back to `SUPABASE_KEY` if empty. Needed when `SUPABASE_KEY` is `sb_publishable_*` format.
- **Topbar login-only auth**: Token card removed from topbar layout. 401 → `Auth.logout()` → redirect `/admin/login` (admin) or `/login` (client). Token card still works in `admin-legacy.html` (sidebar).
- **`login.js` dual-mode**: Detects `/admin/login` vs `/login` path for different session keys (`vejapro_supabase_session` vs `vejapro_client_session`) and redirect targets (`/admin` vs `/client`).
- **Public CSS cache-busting**: `public-shared.css?v=1.0` — bump `?v=` in ALL public HTML `<link>` and `<script>` tags when changing shared CSS/JS.

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
- `backend/API_ENDPOINTS_CATALOG.md` — all 78 API endpoints
- `backend/docs/ADMIN_UI_V3.md` — admin UI architecture (V6.0 design system + Ops V1)
- `backend/SCHEDULE_ENGINE_V1_SPEC.md` — schedule engine spec (LOCKED)
- `backend/GALLERY_DOCUMENTATION.md` — gallery feature
- `backend/docs/FIGMA_BRIEF_PUBLIC.md` — Figma brief: public/landing pages (4 screens)
- `backend/docs/FIGMA_BRIEF_CLIENT.md` — Figma brief: client portal (6 screens, hash router SPA)
- `backend/docs/FIGMA_BRIEF_ADMIN.md` — Figma brief: admin panel (15 screens, light/dark themes)
