# VejaPRO Projekto Statusas

Paskutinis atnaujinimas: **2026-02-09**

---

## Skaiciai

| Metrika | Kiekis |
|---------|--------|
| API endpointai | 83 (68 API + 15 app) |
| Feature flags | 20 |
| Testu funkcijos | 150 (21 failas) |
| DB migracijos | 16 (HEAD: `000016`) |
| HTML puslapiai | 14 (visi LT, responsive) |

---

## Moduliu statusas

Legenda: DONE = kodas + testai, DONE* = kodas be testu, OFF = neimplementuota/stub.

### Pagrindas (visada aktyvus)

| Modulis | Statusas | Testai | Pastaba |
|---------|----------|--------|---------|
| Projektu CRUD + evidence + sertifikavimas | DONE | 6 | |
| Statusu masina (transition_service) | DONE | 6 | Forward-only, audit, RBAC |
| Auth (JWT, RBAC, require_roles) | DONE | 14 | Supabase HS256 |
| IP allowlist (admin) | DONE* | 0 | Middleware veikia, testo nera |
| Rate limiting | DONE | 1 | |
| PII redakcija audit loguose | DONE | 7 | |
| Security headers (HSTS, CSP, X-Frame) | DONE* | 0 | Testo nera |
| Admin UI (14 puslapiu) | DONE | — | Visi sulietuvinti |

### Mokejimai

| Modulis | Flag | Statusas | Testai | Pastaba |
|---------|------|----------|--------|---------|
| Manual payments (cash/bank) | `enable_manual_payments=true` | DONE | 14 | Default, idempotentiskas |
| Stripe payments | `enable_stripe=false` | DONE | 1 | Optional, TEST rezimas |
| Deposit waive | su manual payments | DONE | — | Admin-only |
| Email patvirtinimas (CERTIFIED->ACTIVE) | — | DONE | 13 | Default V2.3 |
| SMS patvirtinimas (legacy) | `enable_twilio=true` | DONE | 4 | Legacy kanalas |

### Planavimas ir komunikacija

| Modulis | Flag | Statusas | Testai | Pastaba |
|---------|------|----------|--------|---------|
| Call Assistant | `enable_call_assistant=false` | DONE | 8 | |
| Calendar / Appointments | `enable_calendar=false` | DONE | — | Su call assistant |
| Schedule Engine (HOLD, RESCHEDULE, daily) | `enable_schedule_engine=false` | DONE | 17 | |
| Voice webhook (Twilio) | `enable_twilio=true` | DONE | 4 | |
| Chat webhook | `enable_call_assistant=false` | DONE | 4 | |
| Notification outbox (SMS/email/WhatsApp) | `enable_notification_outbox=true` | DONE | 1 | Worker: `enable_recurring_jobs` |

### Email Intake (V2.2 Unified Client Card)

| Modulis | Flag | Statusas | Testai | Pastaba |
|---------|------|----------|--------|---------|
| Intake state / questionnaire | `enable_email_intake=false` | DONE* | **0** | **REIKIA TESTU** |
| Prepare / send offer | `enable_email_intake=false` | DONE* | **0** | **REIKIA TESTU** |
| Public offer view / respond | `enable_email_intake=false` | DONE* | **0** | **REIKIA TESTU** |
| Activation confirm (public) | `enable_email_intake=false` | DONE* | **0** | **REIKIA TESTU** |

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

### Neimplementuota / Stub

| Modulis | Statusas | Pastaba |
|---------|----------|---------|
| WhatsApp API | STUB | Loguoja, bet nesiuncia. Flag: `enable_whatsapp_ping=false` |
| CDN nuotraukoms | OFF | Neprivalomas |
| Redis cache | OFF | Neprivalomas |

---

## CI / CD

| Kas | Statusas | Pastaba |
|-----|----------|---------|
| `ruff check` + `ruff format` | PASS | CI lint job, ruff 0.15.0 |
| `pytest` (150 testu) | PASS | 120 passed, 30 skipped, 0 failed |
| GitHub Actions CI | DONE | lint -> tests (SQLite, in-process) |
| GitHub Actions Deploy | DONE | Manual dispatch, SSH + restart |
| Automatinis deploy (timer) | DONE | `vejapro-update.timer` kas 5 min |

### CI spragos

- [ ] Deploy skriptas **nepaleidzia Alembic migraciju** — tik `git pull` + `restart`
- [ ] Deploy **nekviecia `/health`** — tik `systemctl is-active`

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
- [x] `.env.prod` su `DATABASE_URL`

### Liko padaryti

- [ ] **P0: Twilio LIVE raktai** — perjungti is TEST (SID, AUTH_TOKEN, FROM_NUMBER)
- [ ] **P0: Stripe LIVE raktai** — jei `ENABLE_STRIPE=true` (SECRET_KEY, WEBHOOK_SECRET)
- [ ] **P0: SMTP konfig** — SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SMTP_FROM_EMAIL
- [ ] **P0: CORS** — `CORS_ALLOW_ORIGINS` siuo metu tuscias
- [ ] **P0: `ENABLE_RECURRING_JOBS=true`** — be sito outbox nedispatchina, HOLD neexpiryna
- [ ] **P0: Alembic upgrade head** — patikrinti kad serveryje `000016`
- [ ] **P0: Smoke test** — pilnas srautas DRAFT->ACTIVE su LIVE raktais
- [ ] **P0: Email intake smoke test** — call request -> anketa -> offer -> accept
- [ ] **P1: Email Intake testai** — 7 endpointai, 0 testu
- [ ] **P2: Deploy pipeline** — prideti Alembic + health check
- [ ] **P2: IP allowlist testas**
- [ ] **P2: Security headers testas**
- [ ] **P3: WhatsApp API** (vietoj stub)
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
