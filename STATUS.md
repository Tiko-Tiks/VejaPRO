# VejaPRO Projekto Statusas

Paskutinis atnaujinimas: **2026-02-22** (V3.5.2)

---

## Skaiciai

| Metrika | Kiekis |
|---------|--------|
| API endpointai | 78 (API routeriai) + 26 (app UI/health routes) |
| Feature flags | 28 |
| Testu failu | 35 |
| DB migracijos | 17 (HEAD: `000017`) |
| HTML puslapiai | 23 (visi LT, responsive; 22 app + 1 Twilio verif.) |
| Static assets | 3 CSS + 10 JS (`admin-shared`, `public-shared`, `login` + page JS) |

---

## Moduliu statusas

Legenda: DONE = kodas + testai, DONE* = kodas be testu, IN_PROGRESS = daroma, OFF = neimplementuota/stub.

### Pagrindas (visada aktyvus)

| Modulis | Statusas | Testai | Pastaba |
|---------|----------|--------|---------|
| Projektu CRUD + evidence + sertifikavimas | DONE | 6 | |
| Statusu masina (transition_service) | DONE | 39 | Forward-only, audit, RBAC, PII redaction, guards |
| Auth (JWT, RBAC, require_roles) | DONE | 14 | Supabase HS256 + ES256 (JWKS), dual algorithm verification |
| Admin login (Supabase opt-in) | DONE | 6 | `/admin/login`, sessionStorage-only, `/api/v1/auth/refresh`, topbar: login-only (no token card) |
| Client access email (magic link) | DONE | — | `POST /admin/projects/{id}/send-client-access`, 7-dienu JWT |
| IP allowlist (admin) | DONE | 10 | Unit + middleware testai |
| Rate limiting | DONE | 1 | |
| PII redakcija audit loguose | DONE | 7 | |
| Security headers (HSTS, CSP, X-Frame) | DONE | 10 | 6 antrastes, enable/disable |
| Admin UI V6.0 (light/dark toggle, SaaS styling, work queue) | DONE | — | `admin-shared.css/js`, theme toggle, work queue dashboard, `?v=6.9` |
| Admin UI: Klientu modulis (list + profilis) | DONE | — | `/admin/customers` + `/admin/customers/{client_key}` |
| Admin UI: Projektai (V3 migracija) | DONE | — | `projects.html` + `admin-projects.js` |
| Admin UI: kitu puslapiu migracija (Faze C) | DONE | — | calls/calendar/audit/margins/finance/ai-monitor (V3.1 token-card + sidebar) |

| Admin Ops V1 shell + planner/day/project/client | DONE | 8 | `ENABLE_ADMIN_OPS_V1`; `/admin`, `/admin/project/{id}`, `/admin/client/{client_key}` |
| Admin Ops read-model API (day/inbox/client-card) | DONE | 8 | `/api/v1/admin/ops/day/{date}/plan`, `/api/v1/admin/ops/inbox`, `/api/v1/admin/ops/client/{client_key}/card` |
| Planner inbox: ištrinti užklausą (call_request) | DONE | — | Mygtukas „Ištrinti“ prie kiekvienos skambučio užklausos; `DELETE /admin/call-requests/{id}`; skriptas `scripts/cleanup_test_inbox_data.py` ir `scripts/cleanup_test_call_requests.sql` testiniams duomenims valyti |
| Admin Archive (M9 minimal) | DONE* | — | `/admin/archive` su topbar paieska ir grupavimu pagal klienta/projekta |

### Mokejimai

| Modulis | Flag | Statusas | Testai | Pastaba |
|---------|------|----------|--------|---------|
| Manual payments (cash/bank) | `enable_manual_payments=true` | DONE | 14 | Default, idempotentiskas |
| Stripe payments | `enable_stripe=false` | ATIDETA | 1 | Ateities opcija, ne dabartinis prioritetas |
| Deposit waive | su manual payments | DONE | — | Admin-only |
| Email patvirtinimas (CERTIFIED->ACTIVE) | — | DONE | 13 | Default V2.3 |
| SMS patvirtinimas (legacy) | `enable_twilio=true` | ATIDETA | 4+9 | Legacy kanalas, ateities opcija — derinama su vietiniu tiekėju (skambučiai→tekstas→email) |

### Planavimas ir komunikacija

| Modulis | Flag | Statusas | Testai | Pastaba |
|---------|------|----------|--------|---------|
| Call Assistant | `enable_call_assistant=false` | DONE | 8 | |
| Calendar / Appointments | `enable_calendar=false` | DONE | — | Su call assistant |
| Schedule Engine (HOLD, RESCHEDULE, daily) | `enable_schedule_engine=false` | DONE | 17 | |
| Voice webhook (Twilio) | `enable_twilio=true` | ATIDETA | 4 | Ateities opcija — vietinis tiekėjas perduos skambučius tekstu per email |
| Chat webhook | `enable_call_assistant=false` | ATIDETA | 4 | Ateities opcija |
| WhatsApp API (Twilio) | `enable_whatsapp_ping=true` | ATIDETA | 26 | Sandbox, ateities opcija |
| Notification outbox (SMS/email/WhatsApp) | `enable_notification_outbox=true` | DONE | 26 | Email primary, WhatsApp secondary, SMS legacy, email templates centralizuoti per `email_templates.py` |

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

### Viesi puslapiai (Public Frontend V1.0)

| Modulis | Statusas | Pastaba |
|---------|----------|---------|
| Landing page (`/`) redesign | DONE | Hero, featured works, paslaugos, procesas, kainos, garantijos, lead forma, footer, mobile sticky bar |
| Gallery (`/gallery`) redesign | DONE | Sticky filtrai, 4:3 kortelės, infinite scroll, before/after lightbox, empty state |
| Client login (`/login`) | DONE | Supabase auth -> `/client`, dual-mode (admin/client) |
| Client register (`/register`) | DONE | Supabase signUp, el. pašto patvirtinimas |
| Public design system | DONE | `public-shared.css` (1012 eil.) + `public-shared.js` (215 eil.), green/gold paletė |
| Client estimate V3 (vienas šaltinis tiesos) | DONE | `addons_selected[]`, kaina tik iš `/price`, out-of-order (AbortController + priceSeq), 409 handling, `pricing_mode` iš rules, `GET /client/schedule/available-slots` (ENABLE_SCHEDULE_ENGINE), email iš JWT (ne iš formos), atstumo skaičiavimas 2-ame žingsnyje (Nominatim geocoding + rankinis override) |
| Client projekto detalės: antro vizito pasirinkimas | DONE | `visits[]` (VisitInfo), `can_request_secondary_slot`, `preferred_secondary_slot`, `POST /client/projects/{id}/preferred-secondary-slot`, slot picker UI |

### AI

| Modulis | Flag | Statusas | Testai | Pastaba |
|---------|------|----------|--------|---------|
| Intent parsing (multi-provider) | `enable_ai_intent=false` | DONE | 32 | Groq/Claude/OpenAI/Mock |
| Vision AI | `enable_ai_vision=false` | ATIDETA | — | Ateities opcija, neprivalomas — bus plėtojamas vėliau |
| Finance AI extract | `enable_ai_finance_extract=false` | DONE | — | Proposal-only (ne auto-confirm) |
| AI monitoring dashboard | — | DONE | — | `ai-monitor.html` |
| AI Conversation Extract | `enable_ai_conversation_extract=false` | DONE | 23 | Claude Haiku 4.5, budget retry, intake auto-fill |
| AI Email Sentiment | `enable_ai_email_sentiment=false` | DONE | 8 | NEGATIVE/NEUTRAL/POSITIVE, reason_codes, idempotency per Message-Id, CAS |
| AI Pricing (Admin) | `enable_ai_pricing=false` | DONE | 20 | Deterministine baze + LLM korekcija (±20%), fallback mode, fingerprint stale guard, admin decide (approve/edit/ignore), survey, decision hard-gate |

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
| `pytest` | PASS | 35 test failu, CI green |
| GitHub Actions CI | DONE | lint -> tests (SQLite, in-process) |
| GitHub Actions Deploy | DONE ✅ | HTTPS webhook per Cloudflare Tunnel |
| Automatinis deploy (timer) | DONE ✅ | `vejapro-update.timer` kas 5 min — pagrindinis deploy budas |

### CI spragos

- [x] Deploy kviecia `/health` (curl + JSON tikrinimas)
- [x] ~~**GitHub Actions Deploy**~~ — HTTPS webhook per Cloudflare Tunnel (ne SSH)
- [x] Auto-deploy timer/webhook atnaujina koda ir restartina servisa (be Alembic)
- [x] Alembic migracijos vykdomos rankiniu budu serveryje po nauju migraciju

---

## Production konfiguracija

### Atlikta

- [x] Serveris veikia (Ubuntu 25.04, systemd, Nginx)
- [x] Domenas `vejapro.lt` su Cloudflare
- [x] SSL/TLS per Cloudflare
- [x] Auto-deploy timer
- [x] Backup timer
- [x] Health check timer
- [x] 17 Alembic migraciju applied serveryje
- [x] `.env` su `DATABASE_URL` (service pakeistas is `.env.prod` i `.env`)
- [x] SMTP konfig (Hostinger: smtp.hostinger.com:465)
- [x] CORS (`CORS_ALLOW_ORIGINS=https://vejapro.lt,https://www.vejapro.lt`)
- [x] `ENABLE_RECURRING_JOBS=true`
- [x] `ENABLE_EMAIL_INTAKE=true`
- [x] `ENABLE_WHATSAPP_PING=true` (Twilio WhatsApp Sandbox)
- [x] Deploy pipeline su health check; Alembic migracijos vykdomos rankiniu budu
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

**Dabartinis fokusas:** Viskas per email. Twilio/Stripe/Vision AI atidėti — bus plėtojami kaip ateities opcijos.
**Vietinis tiekėjas:** Derinama su vietiniu tiekėju, kuris perduos skambučių turinį tekstu tiesiai į email — tai palengvins analizę be Twilio.

#### Atlikta
- [x] ~~Admin UI sutvarkymas~~ — dashboard su realiais API duomenimis, intake integracija (V2.6)
- [x] ~~Auth (prisijungimas)~~ — Supabase login/logout, sessionStorage, `/api/v1/auth/refresh` (V2.7.2)
- [x] ~~Supabase credentials~~ — SUPABASE_URL, SUPABASE_KEY, JWT_SECRET serveryje
- [x] ~~Pilnas E2E testavimas~~ — DRAFT→ACTIVE srautas (`test_smoke_full_flow.py`: 3 E2E testai)
- [x] ~~Email intake E2E~~ — call request → anketa → offer → accept
- [x] ~~Auto-deploy timer fix~~ — `chown` po `git pull` (V2.5)
- [x] ~~GitHub Actions Deploy fix~~ — HTTPS webhook per Cloudflare Tunnel (V2.5.1)
- [x] ~~Twilio domeno verifikacija~~ — HTML failas servuojamas (V2.5.1)
- [x] ~~WhatsApp API~~ — implementuota V2.5 (Twilio WhatsApp API, Sandbox)
- [x] ~~RESCHEDULE scope (DAY/WEEK) Admin UI~~

#### Ateities plėtra (ne dabartinis prioritetas)
- [ ] **Twilio integracija** — LIVE raktai + voice/SMS/WhatsApp (alternatyva: vietinis tiekėjas skambučiai→tekstas→email)
- [ ] **Stripe LIVE** — jei `ENABLE_STRIPE=true` (SECRET_KEY, WEBHOOK_SECRET)
- [ ] **Vision AI** — nuotraukų analizė (neprivalomas, plėtojamas vėliau)
- [ ] **Redis cache**
- [ ] **CDN nuotraukoms**

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
| 02-09 | V2.4 | Email intake 30 testu, IP/security 10 testu, deploy pipeline (health + webhook/timer), flag_modified fix, naive/aware datetime fix |
| 02-10 | V2.4.1 | Production fix: .env.prod → .env, staging atnaujintas, deploy diagnostika, Cloudflare Tunnel patvirtintas |
| 02-10 | V2.5 | SMS → Email + WhatsApp migracija: WhatsApp stub → Twilio API, reschedule email+WhatsApp, 26 outbox testai, Sandbox deployed |
| 02-10 | V2.5.1 | Deploy webhook (SSH→HTTPS), +48 unit testai, CI fix (pytest green + ruff), GitHub Actions Deploy veikia |
| 02-10 | V2.6 | Admin UI: dashboard su realiais API duomenimis (projektai/skambučiai/vizitai/auditas), intake state loading iš API calls.html |
| 02-10 | V2.6.1 | Admin UI V3: shared design system + sidebar, klientų modulis, `/admin/projects` migracija (workflow-only, be inline CSS) |
| 02-10 | V2.6.2 | Infra: `INFRASTRUCTURE.md` runbook + `SYSTEM_CONTEXT.md` atnaujintas (Python/venv, timeriai, `.env.prod` symlink backup) |
| 02-10 | V2.6.3 | Admin UI: Fazė C baigta (calls/calendar/audit/margins/finance/ai-monitor) + vienodas `?v=3.1` cache busting |
| 02-11 | V2.6.4 | AI Conversation Extract (23 testai), CloudMailin email webhook (24 testai), Email auto-reply (21 testai) |
| 02-12 | V2.7 | AI Email Sentiment Analysis (8 testai): NEGATIVE/NEUTRAL/POSITIVE klasifikacija, reason_codes, idempotency, CAS, sentiment pill calls.html |
| 02-12 | V2.7.1 | Security hardening: RBAC role tik is `app_metadata`, trusted proxy modelis (`TRUSTED_PROXY_CIDRS`), `admin/token` shared secret, CloudMailin auth fail-closed, Claude model/`system` prompt atnaujinimas |
| 02-12 | V2.7.2 | Forwarded-header hardening: `x-forwarded-*` naudojami tik is trusted proxy (Twilio URL validacija + security headers middleware), prideti testai spoofing scenarijams |
| 02-12 | V2.8 | Admin UI V5.1 konsolidacija (shared CSS komponentai, vienodas `?v=5.1`, `#fafaf9` → CSS kintamieji), email sablonu centralizacija (`email_templates.py`, 6 testai) |
| 02-12 | V2.9 | Admin UI V5.3 funkcionalumo fix: auth flow (token secret, Supabase detection), form auto-styling CSS, auth checks visuose 7 puslapiuose, kalendoriaus supaprastinimas (`<details>`), LT vertimai (filter chips, etiketes, placeholder'iai), graceful empty states, `?v=5.3` cache-bust |
| 02-13 | V3.0 | Admin UI V6.0: light/dark tema su toggle mygtuku sidebar'e (localStorage persist, FOUC prevencija), dashboard redesign (triage kortelės → darbo eilė lentelė su prioriteto taškais, Aktyvūs/Archyvas tabs), SaaS stilistika (pašalintos dekoracijos: noise SVG, gradientai, glass pseudo-elementai, glow shadows), visi hardcoded spalvos pakeistos CSS kintamaisiais, `?v=6.0` cache-bust visuose 11 admin HTML failų |
| 02-13 | V3.1 | Admin Ops V1 iteracija: feature-flag route switch (`/admin` -> planner), `admin/ops` API (day plan, inbox, client card), Project Day + Client Card puslapiai, Archyvas (`/admin/archive`) kaip topbar darbinis paieškos ekranas, `backend/tests/test_admin_ops.py` praplėstas (8 testai) |
| 02-13 | V3.2 | Auth: ES256 JWT verifikacija per JWKS (Supabase V2 tokenai), `SUPABASE_ANON_KEY` (legacy anon raktas), token card pašalintas iš topbar (login-only auth), 401→redirect `/login`, galerija be `/admin` nuorodos, kliento prieigos email su magic link (`POST /admin/projects/{id}/send-client-access`), `CLIENT_PORTAL_ACCESS` email šablonas, `?v=6.5` cache-bust |
| 02-13 | V3.3 | Public Frontend V1.0: landing.html pilnas redesign (hero, featured, services, process, pricing, trust, lead form, mobile sticky bar), gallery.html redesign (sticky filters, 4:3 cards, infinite scroll, lightbox), `public-shared.css` + `public-shared.js` design system, `/register` (Supabase signUp), `/login` dual-mode (client→`/client`, admin→`/admin`), admin login perkeltas į `/admin/login` |
| 02-14 | V3.4 | AI Pricing scope: nauji admin pricing endpointai (`/api/v1/admin/pricing/{project_id}/generate|decide|survey`), pricing service su deterministic base + clamped LLM adjustment (±20%) + fallback + fingerprint idempotency + decision hard-gate, client-card read-model papildytas `pricing_project_id`, `ai_pricing`, `ai_pricing_meta`, `ai_pricing_decision`, `extended_survey`, admin-client-card UI perkelta į pricing workflow (Generate/Approve/Edit/Ignore + survey), 20 testų |
| 02-22 | V3.5 | Client estimate V3: `addons_selected[]` vienas šaltinis tiesos, `pricing_mode`, live re-pricing, out-of-order apsauga (AbortController + priceSeq), legacy `mole_net` → addons, nežinomas addon → 400, 5 nauji testai |
| 02-22 | V3.5.1 | Client portalas: email iš JWT (pašalintas iš EstimateSubmitRequest), atstumo skaičiavimas 2-ame žingsnyje (Nominatim geocoding su User-Agent + rankinis km override), antro vizito pasirinkimas projekto detaliuose (`visits[]`, `can_request_secondary_slot`, `POST /client/projects/{id}/preferred-secondary-slot`, slot picker UI) |
| 02-22 | V3.5.2 | Admin Client Card expandable projektai: `<details>` eilutės su 5 sub-sekcijomis (estimate, mokėjimai, dokumentai, vizitai, išlaidos), `build_estimate_info` perkeltas į service sluoksnį, batch užklausos vizitams/išlaidoms, PII maskavimas, finance_ledger gated expenses. Planner inbox: „Ištrinti" mygtukas skambučių užklausoms (`DELETE /admin/call-requests/{id}`), cleanup skriptai. Client portalas: pašalinta perteklinė statuso kortelė, dokumentų mygtukai. `?v=6.9` cache-bust visuose 14 admin HTML failuose. |
