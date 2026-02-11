# VejaPRO Backend

## 1. Greitas startas

### 1.1 Aplinkos paruosimas

```bash
git clone <repo-url>
cd VejaPRO

# Virtualenv (Ubuntu serveryje jau sukurtas: .venv/)
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt

# Konfiguracija
cp backend/.env.example backend/.env
# -> uzpildyk PRIVALOMAS reiksmes (bent DATABASE_URL, SUPABASE_JWT_SECRET)
```

Minimaliai veikia su: `DATABASE_URL` (SQLite testams) ir `SUPABASE_JWT_SECRET`.

### 1.2 Testu paleidimas

**Pagrindinis budas (be serverio, in-process):**
```bash
cd ~/VejaPRO
source .venv/bin/activate
set -a && . ./backend/.env && set +a
PYTHONPATH=backend python -m pytest backend/tests -v --tb=short
```

Pastaba del timezone (svarbu CI/testams):
- CI naudoja SQLite; `DateTime(timezone=True)` reiksmes saugomos kaip naive datetimes.
- Vengti timezone-aware vs naive datetime palyginimu.

**Su paleistu serveriu (opt-in):**
```bash
# 1 terminalas: serveris
export DATABASE_URL="sqlite:////tmp/veja_api_test.db"
export SUPABASE_JWT_SECRET="testsecret_testsecret_testsecret_test"
export ALLOW_INSECURE_WEBHOOKS=true
export PYTHONPATH=backend
python -c "from app.core.dependencies import engine; from app.models.project import Base; Base.metadata.drop_all(engine); Base.metadata.create_all(engine)"
uvicorn app.main:app --host 127.0.0.1 --port 8001

# 2 terminalas: testai
export BASE_URL="http://127.0.0.1:8001"
export USE_LIVE_SERVER=true
export SUPABASE_JWT_SECRET="testsecret_testsecret_testsecret_test"
PYTHONPATH=backend python -m pytest backend/tests/api -v --tb=short
```

### 1.3 Kodo kokybe (Ruff)

Ruff paleidžiamas **Ubuntu serveryje** (jei lokaliai, pvz. Windows, nėra įdiegtas): SSH į VM, repo root (arba worktree), tada:

```bash
cd ~/VejaPRO   # arba worktree kelias
source .venv/bin/activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt   # jei dar ne
ruff check backend          # Lint
ruff format backend --check # Tikrinti formatavimą (CI)
ruff format backend         # Pataisyti formatavimą
ruff check backend --fix    # Auto-fix (I001, W292 ir kt.)
```

Lokaliai (Linux/macOS): tą patį iš repo root, jei `ruff` įdiegtas. **CI** (GitHub Actions) taip pat bėga ant Ubuntu ir paleidžia `ruff check backend/` bei `ruff format backend/ --check --diff`.

Detalios taisykles ir CI klaidu sprendimai: [LINTING.md](./LINTING.md)

---

## 2. Architektura

### 2.1 Katalogu struktura

```
backend/
├── app/
│   ├── main.py              # FastAPI app, middleware, route mounting
│   ├── api/v1/
│   │   ├── projects.py      # Core: projektai, mokejimai, sertifikavimas, webhooks
│   │   ├── finance.py       # Finance: ledger, quick-payment, AI extract, SSE metrics
│   │   ├── schedule.py      # Schedule Engine: HOLD, RESCHEDULE, daily-approve
│   │   ├── assistant.py     # Call assistant + calendar appointments
│   │   ├── intake.py        # Email intake (Unified Client Card)
│   │   ├── twilio_voice.py  # Twilio Voice webhook
│   │   ├── chat_webhook.py  # Chat webhook
│   │   ├── ai.py            # AI monitoring dashboard
│   │   ├── admin_customers.py      # Admin: klientu sarasas + profilis
│   │   ├── admin_dashboard.py     # Admin: dashboard (hero, triage, SSE)
│   │   ├── admin_project_details.py # Admin: projekto mokejimai, patvirtinimai, pranesimai
│   │   ├── client_views.py  # Client UI V3: dashboard, project view, estimate, services, actions
│   │   └── deploy.py        # Deploy webhook (GitHub Actions)
│   ├── core/
│   │   ├── config.py        # Settings (visi env kintamieji) — SINGLE SOURCE OF TRUTH
│   │   ├── auth.py          # JWT autentifikacija + RBAC (require_roles)
│   │   ├── dependencies.py  # SQLAlchemy engine + SessionLocal
│   │   ├── image_processing.py
│   │   └── storage.py       # Supabase storage
│   ├── models/
│   │   └── project.py       # Visi SQLAlchemy modeliai (17+ lenteliu)
│   ├── schemas/
│   │   ├── project.py       # ProjectStatus enum, Pydantic schemas
│   │   ├── finance.py, intake.py, schedule.py, assistant.py
│   ├── services/
│   │   ├── transition_service.py  # Statusu perejimai + ALLOWED_TRANSITIONS + audit
│   │   ├── intake_service.py      # Email intake logika
│   │   ├── notification_outbox.py # Asinchroninis SMS/email/WhatsApp
│   │   └── recurring_jobs.py      # Background workeriai
│   ├── utils/                     # rate_limit, alerting, pdf_gen, logger
│   ├── static/                    # 17 HTML failu (lietuviu kalba)
│   └── migrations/versions/       # 16+ Alembic migraciju
├── tests/                         # pytest testai (ASGI in-process)
├── .env.example                   # Visi env kintamieji su paaiskinimai
├── requirements.txt
└── requirements-dev.txt
```

### 2.2 Uzklausos srautas (Request Flow)

```
HTTP Request
  -> main.py middleware (security headers, IP allowlist, rate limit)
  -> api/v1/*.py router endpoint
  -> core/auth.py (JWT decode, role check via require_roles)
  -> core/dependencies.py (get_db session)
  -> services/*.py (verslo logika)
  -> models/project.py (SQLAlchemy ORM)
  -> DB (PostgreSQL prod / SQLite tests)
```

### 2.3 Statusu masina (KRITICNE)

```
DRAFT -> PAID -> SCHEDULED -> PENDING_EXPERT -> CERTIFIED -> ACTIVE
```

- **Forward-only** (atgal negalima)
- **Vienintelis kelias:** `POST /api/v1/transition-status`
- Kiekvienas perejimas turi **RBAC** ir **audit log**
- Verslo taisykles: zr. `VEJAPRO_KONSTITUCIJA_V2.md`
- Kodas: `transition_service.py::ALLOWED_TRANSITIONS` + `apply_transition()`

Pagrindiniai guard'ai:
- DRAFT->PAID: reikia DEPOSIT mokejimo fakto (`is_deposit_payment_recorded()`)
- CERTIFIED->ACTIVE: reikia FINAL mokejimo + kliento patvirtinimo (`is_client_confirmed()`)

### 2.4 Feature Flags

Visos flags apibreztos `config.py::Settings` klaseje.
Pilnas sarasas su paaiskinimai: `.env.example`.

Jei modulis isjungtas, atitinkami endpointai grazina **404** (ne 403).

### 2.5 Autentifikacija ir RBAC

- JWT tokenai (Supabase-issued arba vidinis admin token)
- 4 roles: `ADMIN`, `SUBCONTRACTOR`, `EXPERT`, `CLIENT`
- `require_roles("ADMIN")` dekoratorius admin endpointuose
- `ADMIN_IP_ALLOWLIST` — papildomas IP filtras admin endpointams

---

## 3. Dokumentacija

### Privalomi (pries programuojant)

1. **[VEJAPRO_KONSTITUCIJA_V2.md](./VEJAPRO_KONSTITUCIJA_V2.md)** — verslo logika, statusu taisykles, RBAC, mokejimu doktrina
2. **[VEJAPRO_TECHNINE_DOKUMENTACIJA_V2.md](./VEJAPRO_TECHNINE_DOKUMENTACIJA_V2.md)** — DB schema, state machine, API spec, architekturos sablonai
3. **[API_ENDPOINTS_CATALOG.md](./API_ENDPOINTS_CATALOG.md)** — pilnas API endpointu katalogas (pagal koda)

### Papildomi (pagal moduli)

- [SCHEDULE_ENGINE_V1_SPEC.md](./SCHEDULE_ENGINE_V1_SPEC.md) — planavimo masinos logika
- [SCHEDULE_ENGINE_BACKLOG.md](./SCHEDULE_ENGINE_BACKLOG.md) — likusiu darbu sarasas
- [CONTRACTOR_EXPERT_PORTALS.md](./CONTRACTOR_EXPERT_PORTALS.md) — rangovo/eksperto portalai
- [GALLERY_DOCUMENTATION.md](./GALLERY_DOCUMENTATION.md) — galerijos modulis
- [LINTING.md](./LINTING.md) — ruff taisykles ir CI klaidu fix
- [docs/ADMIN_UI_V3.md](./docs/ADMIN_UI_V3.md) — Admin UI V3 (shared design system, sidebar, Klientu modulis, migracijos taisykles)

### Infrastruktura ir deploy

- [INFRASTRUCTURE.md](../INFRASTRUCTURE.md) — trumpas runbook (kur veikia production, kaip deployinti)
- [SYSTEM_CONTEXT.md](../SYSTEM_CONTEXT.md) — SSH, deploy, systemd, troubleshooting, CI/CD

### Archyvas (istoriniai dokumentai)

Auditu ataskaitos, deployment notes, impact analysis: [docs/archive/](./docs/archive/)

---

## 4. Admin UI

| Kelias | Paskirtis |
|--------|-----------|
| `/admin` | Dashboard — Šiandienos prioritetai (hero, triage, klientai) |
| `/admin/projects` | Projektu valdymas |
| `/admin/calls` | Skambuciu uzklauso + intake anketa |
| `/admin/calendar` | Kalendorius + Schedule Engine |
| `/admin/audit` | Audito zurnalas |
| `/admin/margins` | Marzu taisykles |
| `/admin/customers` | Klientu sarasas |
| `/admin/customers/{client_key}` | Kliento profilis |
| `/admin/finance` | Finansu knyga (ledger, dokumentai, taisykles) |
| `/admin/ai` | AI monitoring dashboard |

Token saugomas narsykleje: `vejapro_admin_token`.

Admin UI V3.3 (Operator Workflow) bendri asset'ai:
- CSS: `/static/admin-shared.css?v=3.3`
- JS: `/static/admin-shared.js?v=3.3`
- Sidebar: 240px, fono spalva #1a1a2e, token generatorius apačioje
- Dashboard: `GET /api/v1/admin/dashboard`, triage SSE `GET /api/v1/admin/dashboard/sse`

### Viesieji portalai

| Kelias | Paskirtis | Prieiga |
|--------|-----------|---------|
| `/` | Pradinis puslapis, uzklauso forma | Viesa |
| `/gallery` | Viesoji projektu galerija | Viesa |
| `/chat` | Web chat widget | Viesa |
| `/client` | Klientu portalas (projekto eiga) | JWT |
| `/contractor` | Rangovo portalas | JWT |
| `/expert` | Eksperto portalas (sertifikavimas) | JWT |

---

## 5. CI/CD

- **CI** (`.github/workflows/ci.yml`): `lint` (ruff 0.15.0) -> `tests` (pytest, SQLite)
- **Deploy** (`.github/workflows/deploy.yml`): manual dispatch -> SSH -> git pull -> systemctl restart
- Automatinis deploy: serveris kas 5 min tikrina `origin/main` (`vejapro-update.timer`)

Detaliau: [INFRASTRUCTURE.md](../INFRASTRUCTURE.md) ir [SYSTEM_CONTEXT.md](../SYSTEM_CONTEXT.md)

---

## 6. Pries pradedant koda

- [ ] Perskaiciau Konstitucija (V2)
- [ ] Perskaiciau Technine Dokumentacija (V2)
- [ ] Suprantu statusu cikla (forward-only, tik per transition-status)
- [ ] Zinau API endpoints (API katalogas)
- [ ] Suprantu feature flags sistema (.env.example)
- [ ] Zinau audit log reikalavimus (privalomas visiems kritiniams veiksmams)

---

## 7. Kontaktai

- **Techniniai klausimai:** tech@vejapro.lt
- **Verslo logika:** product@vejapro.lt
- **Sertifikavimas:** expert@vejapro.lt

---

**KRITINE TAISYKLE:** Pries darydamas bet kokius pakeitimus sistemoje, **VISADA** patikrink Konstitucija.
Jei kazkas priestarauja Konstitucijai — keiciame koda, ne Konstitucija (isskyrus oficialias revizijas).

---

(c) 2026 VejaPRO. Visos teises saugomos.

**Paskutinis atnaujinimas:** 2026-02-11
