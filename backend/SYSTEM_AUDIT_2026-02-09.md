# PILNAS SISTEMOS AUDITAS — ATASKAITA

Data: 2026-02-09

Verdiktas: sistema po V2.3 (email aktyvacija, finance rekonstrukcija) yra **stabili**. CI lint ir testai atitinka taisykles, payments-first ir Konstitucija V1.4 laikomasi. Aptikti keli nedideli dokumentacijos/konfigūracijos neatitikimai ir viena semantinė dvigubos email patvirtinimo endpointų rizika — rekomenduojama ištaisyti.

---

## 1. APIMTIS

Patikrinta:

- Konfigūracija ir feature flags (`config.py`, CI env)
- API endpointai vs katalogas ir Konstitucija V1.4 / Techninė dokumentacija V1.5.1
- Statusų perėjimai (ALLOWED_TRANSITIONS, SYSTEM_EMAIL / SYSTEM_TWILIO)
- Mokėjimai: manual, Stripe, idempotencija, FINAL → email confirmation
- Finance modulis: ledger, quick-payment, SSE metrics, AI extract
- V2.3: `POST /public/confirm-payment/{token}`, `create_client_confirmation(..., channel="email")`, QuickPaymentResponse.email_queued
- Migracijos (000001–000016), deploy workflow, saugumas (PII, SQL, headers)
- Testai ir CI (lint → tests, feature flags)

---

## 2. SVEIKA (viskas gerai)

- **CI**: `lint` be `continue-on-error`, `tests` su `needs: lint`. Ruff check + format atskirai.
- **Feature flags CI**: ENABLE_FINANCE_LEDGER, ENABLE_FINANCE_AI_INGEST, ENABLE_FINANCE_AUTO_RULES, ENABLE_NOTIFICATION_OUTBOX ir kt. aiškiai nurodyti.
- **Transition service**: vienintelis šaltinis `ALLOWED_TRANSITIONS`; CERTIFIED→ACTIVE leidžiami aktoriai `SYSTEM_TWILIO` ir `SYSTEM_EMAIL`.
- **Payments-first**: DEPOSIT/FINAL validuojami per `is_deposit_payment_recorded` / `is_final_payment_recorded`; manual idempotencija per `provider_event_id`.
- **Finance**: `_require_finance_enabled()` visuose finance endpointuose; Quick Payment su row-lock (FOR UPDATE), 409 konfliktui skirtingiems parametrams.
- **V2.3 migracijos**: 000015 (client_confirmations, unified client card), 000016 (payments.ai_extracted_data, UNIQUE(provider, provider_event_id), channel default).
- **Deploy**: naudojamas `envs: DEPLOY_TARGET`, ne `${{ inputs.target }}` shell'e; health check su `sleep 5`.
- **PII**: audit log redakcija per `pii_redaction_enabled` ir `pii_redaction_fields`.
- **Schemos**: QuickPaymentResponse su `email_queued`; FINAL flow naudoja `enqueue_notification` (email), ne tiesioginį SMS.

---

## 3. PROBLEMOS IR REKOMENDACIJOS

### P1 (vidutinė) — Dvigubi email patvirtinimo endpointai, skirtinga validacija

**Faktas:**

- **intake.py**: `POST /api/v1/public/activations/{token}/confirm` — tikrina tik PENDING, nepasibaigusį tokeną, projektą CERTIFIED. **Netikrina** `is_final_payment_recorded()` nei `is_client_confirmed()` per apply_transition (apply_transition viduje ACTIVE reikalauja abiejų).
- **projects.py**: `POST /api/v1/public/confirm-payment/{token}` — pilna V2.3 logika: FINAL payment, attempts, expires_at, `is_final_payment_recorded`, tada `apply_transition(..., SYSTEM_EMAIL)`.

**Poveikis:** Jei klientas gauna nuorodą į `/public/activations/{token}/confirm` (senas intake flow), teoriškai galima būtų aktyvuoti be FINAL mokėjimo, jei apply_transition būtų iškviestas be PAID/FINAL tikrinimo. Iš tikrųjų `apply_transition` CERTIFIED→ACTIVE viduje **tikrina** `is_final_payment_recorded` ir `is_client_confirmed`, todėl abu endpointai galiausiai vienodi pagal rezultatą, bet intake endpointas:
- netikrina attempts (3 max) nei expiry prieš kvietimą,
- grąžina kitokį response formatą (ActivationConfirmResponse),
- nėra dokumentuotas kaip pagrindinis V2.3 kanalas (kataloge pagrindinis yra confirm-payment).

**Rekomendacija:** Laikyti vieną kanoninį endpointą `POST /public/confirm-payment/{token}` (projects.py). Intake `activations/{token}/confirm` arba deprecate (redirect į confirm-payment), arba suvienodinti validaciją (attempts, expiry, FINAL payment) ir response formatą, kad nebūtų semantinio skirtumo.

---

### P2 (žema) — CI: trūksta ENABLE_EMAIL_INTAKE ir ENABLE_FINANCE_METRICS

**Faktas:** `.github/workflows/ci.yml` tests job turi ENABLE_FINANCE_LEDGER, ENABLE_FINANCE_AI_INGEST, ENABLE_FINANCE_AUTO_RULES, bet **nėra**:
- `ENABLE_EMAIL_INTAKE` — reikalingas testams, kurie tikrina `POST /public/confirm-payment/{token}` (404 jei išjungta).
- `ENABLE_FINANCE_METRICS` — jei testai kada nors kreipsis į `GET /admin/finance/metrics`, 404 be flag.

**Rekomendacija:** Pridėti į CI env:
```yaml
ENABLE_EMAIL_INTAKE: "true"
ENABLE_FINANCE_METRICS: "true"
```
Kad feature-flag-gated testai (pvz. test_v23_finance) ir būsimi metrics testai veiktų nuosekliai.

---

### P3 (žema) — Finance quick_payment: SELECT FOR UPDATE be SQLite guard

**Faktas:** `finance.py` quick_payment naudoja `select(Project).where(...).with_for_update()` tiesiogiai. Kituose moduliuose (schedule, twilio_voice, chat_webhook) naudojamas `_with_for_update_if_supported(stmt, db)` su `db.bind.dialect.name == "sqlite"` guard, kad CI (SQLite) nepultų.

**Poveikis:** Priklauso nuo SQLAlchemy/SQLite versijos — kai kuriuose atvejuose SQLite gali ignoruoti FOR UPDATE arba metam klaidą. CI testai su SQLite gali būti nestabilūs jei ši kelias bus vykdomas.

**Rekomendacija:** Naudoti tą patį guard kaip schedule/twilio: įvesti `_with_for_update_if_supported(select(Project).where(Project.id == project_id), db)` ir naudoti jo rezultatą, kad testai su SQLite būtų deterministiški.

---

### P4 (žema) — Audit UI: trūksta SYSTEM_EMAIL aktoriaus

**Faktas:** `backend/app/static/audit.html` actor tipo filtre yra SYSTEM_STRIPE, SYSTEM_TWILIO, bet **nėra SYSTEM_EMAIL**. V2.3 email patvirtinimai audit log'e turi `actor_type=SYSTEM_EMAIL`.

**Rekomendacija:** Pridėti `<option value="SYSTEM_EMAIL">SYSTEM_EMAIL</option>` į actor dropdown, kad admin galėtų filtruoti email patvirtinimus.

---

### P5 (dokumentacija) — PROGRESS_LOCK.md ir katalogas: senas endpoint pavadinimas

**Faktas:** PROGRESS_LOCK.md (apie 350 eil.) vis dar mini `POST /api/v1/public/activations/{token}/confirm` kaip email aktyvavimo endpointą. API_ENDPOINTS_CATALOG_V1.52.md turi ir `activations/{token}/confirm` (2.5), ir `confirm-payment/{token}` (2.6) — abu aprašyti; kataloge 2.6 aiškiai nurodyta kaip „viesas email patvirtinimo endpointas“.

**Rekomendacija:** PROGRESS_LOCK.md atnaujinti: nurodyti kanoninį endpointą `POST /api/v1/public/confirm-payment/{token}` ir pažymėti, kad `activations/{token}/confirm` (intake) yra alternatyvus/senas, jei lieka palaikymas.

---

## 4. KONFIGŪRACIJA — SANTRAUKA

| Flag / kintamasis | Default | Naudojimas |
|-------------------|---------|------------|
| ENABLE_FINANCE_LEDGER | false | Finance ledger, quick-payment, documents, extract |
| ENABLE_FINANCE_METRICS | false | GET /admin/finance/metrics (SSE) |
| ENABLE_FINANCE_AI_INGEST | false | AI extract feature (gali būti naudojamas kartu su ledger) |
| ENABLE_FINANCE_AUTO_RULES | true | Vendor rules finance flow |
| ENABLE_EMAIL_INTAKE | false | Email confirmation (confirm-payment, FINAL → email) |
| FINANCE_METRICS_MAX_SSE_CONNECTIONS | 10 | Max concurrent SSE (429 viršijus) |

Visi šie nurodyti `config.py`; CI turi dalį (P2).

---

## 5. MIGRACIJOS EILĖ

- 000001 init_core_schema
- 000002 add_project_indexes
- 000003 add_call_calendar_tables
- 000004 add_evidences_created_at
- 000005 enable_rls_policies
- 000006 add_foreign_key_indexes
- 000007 schedule_engine_phase0
- 000008 payments_first_manual
- 000009 notification_outbox
- 000010 appointments_status_axis
- 000011 schema_hygiene_constraints
- 000012 enable_rls_for_new_tables
- 000013 add_evidence_image_variants
- 000014 finance_ledger_core
- 000015 unified_client_card_v22 (client_confirmations, call_requests, evidences)
- 000016 v23_finance_reconstruction (payments.ai_extracted_data, uniq_payments_provider_event, client_confirmations channel default)

Produkcijoje prieš deploy būtina: `alembic upgrade head`.

---

## 6. SAUGUMAS (trumpai)

- Admin endpointai: `require_roles("ADMIN")`.
- Public confirm-payment: autentifikacija per token (token_hash lookup), be PII atsakyme.
- Finance SSE: tik agreguoti skaičiai, be PII; riba jungčių ir 429.
- Deploy: secrets per GitHub, env per `envs:`, ne tiesiogiai shell.
- Klaidos: lietuviški pranešimai vartotojui; EXPOSE_ERROR_DETAILS tik dev.

---

## 7. PRIORITETINĖ VEIKSMŲ EILĖ

1. **P2** — Pridėti ENABLE_EMAIL_INTAKE ir ENABLE_FINANCE_METRICS į CI env.
2. **P4** — Pridėti SYSTEM_EMAIL į audit.html actor filtrą.
3. **P3** — Finance quick_payment: SQLite-safe FOR UPDATE (guard).
4. **P1** — Nuspręsti dėl activations vs confirm-payment: deprecate arba suvienodinti validaciją ir dokumentuoti.
5. **P5** — Atnaujinti PROGRESS_LOCK.md (kanoninis confirm-payment endpoint).

---

## 8. ATNAUJINIMAS NUO 2026-02-07 AUDITO

- Ankstesnio audito P1–P5 (schema higiena) **išspręsti** (000011, modelių suvienodinimas).
- P6 (settings dubliavimai): kanoniniai docs_enabled/openapi_enabled su AliasChoices — OK.
- P7 (testai in-process): ASGITransport pagal nutylėjimą — OK.

Šis (2026-02-09) auditas papildo V2.3 pakeitimus: email aktyvacija, finance rekonstrukcija, dvigubi endpointai, CI flags, audit UI.
