# VejaPRO Projekto Statusas

Paskutinis atnaujinimas: **2026-02-12** (V2.7)

---

## Skaiciai

| Metrika | Kiekis |
|---------|--------|
| API endpointai | 79 (API routeriai) + 18 (app UI routes) |
| Feature flags | 26 |
| Testu funkcijos | 374 (33 failu) |
| DB migracijos | 16 (HEAD: `000016`) |
| HTML puslapiai | 17 (visi LT, responsive) |

---

## Moduliu statusas

Legenda: DONE = kodas + testai, DONE* = kodas be testu, IN_PROGRESS = daroma, OFF = neimplementuota/stub.

### Pagrindas (visada aktyvus)

| Modulis | Statusas | Testai | Pastaba |
|---------|----------|--------|---------|
| Projektu CRUD + evidence + sertifikavimas | DONE | 6 | |
| Statusu masina (transition_service) | DONE | 39 | Forward-only, audit, RBAC, PII redaction, guards |
| Auth (JWT, RBAC, require_roles) | DONE | 14 | Supabase HS256 |
| IP allowlist (admin) | DONE | 10 | Unit + middleware testai |
| Rate limiting | DONE | 1 | |
| PII redakcija audit loguose | DONE | 7 | |
| Security headers (HSTS, CSP, X-Frame) | DONE | 10 | 6 antrastes, enable/disable |
| Admin UI V3 (shared CSS/JS + sidebar) | DONE | — | `admin-shared.css/js` |
| Admin UI: Klientu modulis (list + profilis) | DONE | — | `/admin/customers` + `/admin/customers/{client_key}` |
| Admin UI: Projektai (V3 migracija) | DONE | — | `projects.html` + `admin-projects.js` |
| Admin UI: kitu puslapiu migracija (Faze C) | DONE | — | calls/calendar/audit/margins/finance/ai-monitor (V3.1 token-card + sidebar) |

### Mokejimai

| Modulis | Flag | Statusas | Testai | Pastaba |
|---------|------|----------|--------|---------|
| Manual payments (cash/bank) | `enable_manual_payments=true` | DONE | 14 | Default, idempotentiskas |
| Stripe payments | `enable_stripe=false` | DONE | 1 | Optional, TEST rezimas |
| Deposit waive | su manual payments | DONE | — | Admin-only |
| Email patvirtinimas (CERTIFIED->ACTIVE) | — | DONE | 13 | Default V2.3 |
| SMS patvirtinimas (legacy) | `enable_twilio=true` | DONE | 4+9 | Legacy kanalas, sms_service unit testai |

### Planavimas ir komunikacija

| Modulis | Flag | Statusas | Testai | Pastaba |
|---------|------|----------|--------|---------|
| Call Assistant | `enable_call_assistant=false` | DONE | 8 | |
| Calendar / Appointments | `enable_calendar=false` | DONE | — | Su call assistant |
| Schedule Engine (HOLD, RESCHEDULE, daily) | `enable_schedule_engine=false` | DONE | 17 | |
| Voice webhook (Twilio) | `enable_twilio=true` | DONE | 4 | |
| Chat webhook | `enable_call_assistant=false` | DONE | 4 | |
| WhatsApp API (Twilio) | `enable_whatsapp_ping=true` | DONE | 26 | Sandbox, Twilio WhatsApp API |
| Notification outbox (SMS/email/WhatsApp) | `enable_notification_outbox=true` | DONE | 26 | Email primary, WhatsApp secondary, SMS legacy |

### Email Intake (V2.2 Unified Client Card)

| Modulis | Flag | Statusas | Testai | Pastaba |
|---------|------|----------|--------|---------|
| Intake state / questionnaire | `enable_email_intake=true` | DONE | 30 | Admin + public + activation |
| Prepare / send offer | `enable_email_intake=true` | DONE | 30 | Auto-prepare, optimistic lock |
| Public offer view / respond | `enable_email_intake=true` | DONE | 30 | Accept/reject, audit logs |
| Activation confirm (public) | `enable_email_intake=true` | DONE | 30 | CERTIFIED->ACTIVE, token expiry |

### Finansai

| Modulis | Flag | Statusas | Testai | Pastaba |
|---------|------|----------|--------|---------|
| Ledger CRUD + reversal | `enable_finance_ledger=false` | DONE | 31 | |
| Documents upload + AI extract | `enable_finance_ai_ingest=false` | DONE | 31 | |
| Vendor rules | `enable_finance_ledger=false` | DONE | 31 | |
| Quick-payment + transition | `enable_finance_ledger=false` | DONE | 13 | |
| SSE metrics | `enable_finance_metrics=false` | DONE | 1 | |

### Marketing / Gallery

| Modulis | Flag | Statusas | Testai | Pastaba |
|---------|------|----------|--------|---------|
| Gallery endpoint (cursor pagination) | `enable_marketing_module=false` | DONE | 9 | |
| Evidence approval for web | `enable_marketing_module=false` | DONE | 9 | |
| Marketing consent | `enable_marketing_module=false` | DONE | 9 | |

### AI

| Modulis | Flag | Statusas | Testai | Pastaba |
|---------|------|----------|--------|---------|
| Intent parsing (multi-provider) | `enable_ai_intent=false` | DONE | 32 | Groq/Claude/OpenAI/Mock |
| Vision AI | `enable_ai_vision=false` | DONE* | — | Service egzistuoja, nenaudojamas |
| Finance AI extract | `enable_ai_finance_extract=false` | DONE | — | Proposal-only (ne auto-confirm) |
| AI monitoring dashboard | — | DONE | — | `ai-monitor.html` |
| AI Conversation Extract | `enable_ai_conversation_extract=false` | DONE | 23 | Claude Haiku 4.5, budget retry, intake auto-fill |
| AI Email Sentiment | `enable_ai_email_sentiment=false` | DONE | 8 | NEGATIVE/NEUTRAL/POSITIVE, reason_codes, idempotency per Message-Id, CAS |

### Email Webhook & Auto-Reply

| Modulis | Flag | Statusas | Testai | Pastaba |
|---------|------|----------|--------|---------|
| Inbound email webhook (CloudMailin) | `enable_email_webhook=false` | DONE | 24 | Basic Auth, rate limit, idempotency, AI extract+sentiment |
| Email auto-reply (trūkstami duomenys) | `enable_email_auto_reply=false` | DONE | 21 | Conversation tracking, auto-offer, missing-data templates |

### Neimplementuota / Stub

| Modulis | Statusas | Pastaba |
|---------|----------|---------|
| CDN nuotraukoms | OFF | Neprivalomas |
| Redis cache | OFF | Neprivalomas |

---

## CI / CD

| Kas | Statusas | Pastaba |
|-----|----------|---------|
| `ruff check` + `ruff format` | PASS | CI lint job, ruff 0.15.0 |
| `pytest` (374 testu) | PASS | 374 passed, 0 skipped, 0 failed |
| GitHub Actions CI | DONE | lint -> tests (SQLite, in-process) |
| GitHub Actions Deploy | DONE ✅ | HTTPS webhook per Cloudflare Tunnel |
| Automatinis deploy (timer) | DONE ✅ | `vejapro-update.timer` kas 5 min — pagrindinis deploy budas |

### CI spragos

- [x] Deploy skriptas paleidzia Alembic migracijas (`alembic upgrade head`)
- [x] Deploy kviecia `/health` (curl + JSON tikrinimas)
- [x] ~~**GitHub Actions Deploy**~~ — HTTPS webhook per Cloudflare Tunnel (ne SSH)

---

## Production konfiguracija

### Atlikta

- [x] Serveris veikia (Ubuntu 25.04, systemd, Nginx)
- [x] Domenas `vejapro.lt` su Cloudflare
- [x] SSL/TLS per Cloudflare
- [x] Auto-deploy timer
- [x] Backup timer
- [x] Health check timer
- [x] 16 Alembic migraciju applied serveryje
- [x] `.env` su `DATABASE_URL` (service pakeistas is `.env.prod` i `.env`)
- [x] SMTP konfig (Hostinger: smtp.hostinger.com:465)
- [x] CORS (`CORS_ALLOW_ORIGINS=https://vejapro.lt,https://www.vejapro.lt`)
- [x] `ENABLE_RECURRING_JOBS=true`
- [x] `ENABLE_EMAIL_INTAKE=true`
- [x] `ENABLE_WHATSAPP_PING=true` (Twilio WhatsApp Sandbox)
- [x] Deploy pipeline su Alembic + health check
- [x] Email Intake 30 testu (CI PASS)
- [x] IP allowlist + Security headers 10 testu (CI PASS)
- [x] Production serveris veikia — `vejapro.lt/health` → `{"status":"ok","db":"ok"}`
- [x] Staging serveris atnaujintas — kodas V2.4 (`f7b52be`), migracijos applied
- [x] Cloudflare Tunnel veikia (cloudflared.service active)
- [x] Auto-deploy timer veikia ir paima nauja koda

### Issprestu problemu zurnalas

| Data | Problema | Sprendimas |
|------|----------|-----------|
| 02-10 | `vejapro.service` crash loop (`Result: resources`) | `.env.prod` neegzistavo — service pakeistas naudoti `.env` |
| 02-10 | Staging senas kodas (prieš V1.5) | `git pull origin main` + Alembic migracijos + restart |
| 02-10 | GitHub Actions Deploy SSH timeout | Pakeista: HTTPS webhook per Cloudflare Tunnel (`/api/v1/deploy/webhook`) |
| 02-10 | Auto-deploy timer sukuria root-owned git objects | `vejapro-update.service` veikia kaip root — reikia `User=administrator` |

### Liko padaryti

**Sprendimas:** Twilio/Stripe/Supabase lieka TEST rezime kol sistema nebus pilnai paruosta (Admin UI, auth, pilnas flow). LIVE raktai — tik po pilno paruosimo.

- [x] ~~**P1: Admin UI sutvarkymas**~~ — dashboard su realiais API duomenimis, intake integracija calls.html (V2.6)
- [ ] **P1: Auth (prisijungimas)** — Supabase auth integracija, login/logout, sesijos
- [ ] **P1: Supabase credentials** — SUPABASE_URL, SUPABASE_KEY, JWT_SECRET (po auth sutvarkymo)
- [ ] **P1: Pilnas E2E testavimas** — DRAFT->ACTIVE srautas su TEST raktais
- [ ] **P1: Email intake E2E** — call request -> anketa -> offer -> accept (TEST)
- [x] ~~**P1: Auto-deploy timer fix**~~ — pridetas `chown` po `git pull` skripte (V2.5)
- [x] ~~**P1: GitHub Actions Deploy fix**~~ — HTTPS webhook per Cloudflare Tunnel (V2.5.1)
- [x] ~~**P1: Twilio domeno verifikacija**~~ — HTML failas servuojamas (V2.5.1)
- [ ] **P2: Twilio LIVE raktai** — perjungti is TEST kai sistema paruosta
- [ ] **P2: Stripe LIVE raktai** — jei `ENABLE_STRIPE=true` (SECRET_KEY, WEBHOOK_SECRET)
- [ ] **P2: Smoke test su LIVE** — pilnas srautas su tikrais raktais
- [x] ~~**P3: WhatsApp API**~~ — implementuota V2.5 (Twilio WhatsApp API, Sandbox)
- [ ] **P3: Vision AI integracija**
- [ ] **P3: Redis cache**
- [ ] **P3: CDN nuotraukoms**
- [ ] **P3: RESCHEDULE scope (DAY/WEEK) Admin UI**

---

## Versiju istorija

| Data | Versija | Kas padaryta |
|------|---------|-------------|
| 02-03 | V1.0 | Core schema, projektu CRUD, statusu masina, audit, evidences |
| 02-04 | V1.1 | Call assistant, calendar, deploy pipeline |
| 02-05 | V1.2 | RLS policies, foreign key indexes |
| 02-06 | V1.3 | Evidences created_at, Stripe/Twilio webhooks |
| 02-07 | V1.4 | Schedule Engine (HOLD, RESCHEDULE, daily-approve), payments-first, manual payments, notification outbox, voice/chat webhooks |
| 02-08 | V1.5 | Finance module (ledger, documents, AI extract, vendor rules, quick-payment), schema hygiene, image variants |
| 02-09 | V2.2 | Unified Client Card (email intake, multi-channel outbox, client_confirmations, SYSTEM_EMAIL) |
| 02-09 | V2.3 | Finance reconstruction, SSE metrics, AI finance extract, email patvirtinimas (default) |
| 02-09 | — | Dokumentacijos reorganizacija (V2 konsolidacija, .env.example, archyvas, .cursorrules sync) |
| 02-09 | V2.4 | Email intake 30 testu, IP/security 10 testu, deploy pipeline (Alembic + health), flag_modified fix, naive/aware datetime fix |
| 02-10 | V2.4.1 | Production fix: .env.prod → .env, staging atnaujintas, deploy diagnostika, Cloudflare Tunnel patvirtintas |
| 02-10 | V2.5 | SMS → Email + WhatsApp migracija: WhatsApp stub → Twilio API, reschedule email+WhatsApp, 26 outbox testai, Sandbox deployed |
| 02-10 | V2.5.1 | Deploy webhook (SSH→HTTPS), +48 unit testai, CI fix (pytest green + ruff), GitHub Actions Deploy veikia |
| 02-10 | V2.6 | Admin UI: dashboard su realiais API duomenimis (projektai/skambučiai/vizitai/auditas), intake state loading iš API calls.html |
| 02-10 | V2.6.1 | Admin UI V3: shared design system + sidebar, klientų modulis, `/admin/projects` migracija (workflow-only, be inline CSS) |
| 02-10 | V2.6.2 | Infra: `INFRASTRUCTURE.md` runbook + `SYSTEM_CONTEXT.md` atnaujintas (Python/venv, timeriai, `.env.prod` symlink backup) |
| 02-10 | V2.6.3 | Admin UI: Fazė C baigta (calls/calendar/audit/margins/finance/ai-monitor) + vienodas `?v=3.1` cache busting |
| 02-11 | V2.6.4 | AI Conversation Extract (23 testai), CloudMailin email webhook (24 testai), Email auto-reply (21 testai) |
| 02-12 | V2.7 | AI Email Sentiment Analysis (8 testai): NEGATIVE/NEUTRAL/POSITIVE klasifikacija, reason_codes, idempotency, CAS, sentiment pill calls.html |
