# VejaPRO API Endpointu Katalogas (V1.52 + V2.3 + Admin UI V3 + Client UI V3)

Data: 2026-02-11
Statusas: Gyvas (atitinka esama backend implementacija)
Pastaba: kanoniniai principai ir statusu valdymas lieka pagal `VEJAPRO_KONSTITUCIJA_V2.md` (payments-first, V2.3 email aktyvacija). Kliento portalas – backend-driven view modeliai, žr. `backend/docs/CLIENT_UI_V3.md`.

## 0) Bendros taisykles

- Visi endpointai turi prefiksa: `/api/v1`.
- Statusai keiciami tik per `POST /api/v1/transition-status` (forward-only) su audit.
- Auth: naudojamas Supabase JWT (HS256). Role imama is `app_metadata.role`.
- RBAC: roles tik kanonines: `CLIENT`, `SUBCONTRACTOR`, `EXPERT`, `ADMIN` (sistemos aktoriai webhooks: `SYSTEM_STRIPE`, `SYSTEM_TWILIO`, `SYSTEM_EMAIL`).
- Feature flags: jei funkcija isjungta, endpointas turi grazinti `404` (ne `403`) ir neskelbti, kad funkcija egzistuoja.

## 1) Feature Flags (gating)

- `ENABLE_SCHEDULE_ENGINE` – Schedule Engine endpointai.
- `ENABLE_CALL_ASSISTANT` – Call assistant public forma ir admin call-requests/admin appointments.
- `ENABLE_CALENDAR` – legacy/admin appointments endpointai (`/admin/appointments`).
- `ENABLE_MANUAL_PAYMENTS` – manual payments endpointas.
- `ENABLE_STRIPE` – Stripe checkout link endpointas ir Stripe webhook logika.
- `ENABLE_TWILIO` – Twilio SMS webhook logika (aktyvavimas) ir (jei naudojama) SMS siuntimas.
- `ENABLE_EMAIL_INTAKE` – Email intake (Unified Client Card) endpointai.
- `ENABLE_FINANCE_LEDGER` – Finance ledger ir quick-payment endpointai (V2.3).
- `ENABLE_FINANCE_METRICS` – Finance SSE metrics endpointas (V2.3).
- `ENABLE_WHATSAPP_PING` – WhatsApp ping pranesimai (per notification outbox / Twilio).
- `ENABLE_AI_SUMMARY` – Admin dashboard AI summary pill (V3.3).
- `DASHBOARD_SSE_MAX_CONNECTIONS` – Max vienalaikių dashboard SSE jungčių (default 5).
- `EXPOSE_ERROR_DETAILS` – 5xx detales (dev).

## 2) Endpointai pagal moduli (pilnas katalogas)

### 2.1 Projects / Core (`backend/app/api/v1/projects.py`)

- `POST /projects`
  - Paskirtis: sukurti projekta `DRAFT`.
  - Auth: nereikia (public).
  - Side effects: sukuria audit `PROJECT_CREATED` su `actor_type=CLIENT` (actor_id gali buti NULL).

- `GET /projects/{project_id}`
  - Paskirtis: gauti projekto detales (projektas + evidences + audit).
  - Auth: reikia (`CLIENT` savo; `SUBCONTRACTOR` priskirtas; `EXPERT` priskirtas; `ADMIN` visi).

- `GET /client/projects`
  - Paskirtis: kliento projektu sarasas (pagal `client_info.client_id|user_id|id`).
  - Auth: `CLIENT`.

- `GET /contractor/projects`
  - Paskirtis: rangovo priskirtu projektu sarasas.
  - Auth: `SUBCONTRACTOR`.

- `GET /expert/projects`
  - Paskirtis: eksperto priskirtu projektu sarasas.
  - Auth: `EXPERT`.

- `GET /admin/projects`
  - Paskirtis: admin projektu sarasas su filtrais/pagination (LOCK 1.1: nesikeicia, AdminProjectOut).
  - Auth: `ADMIN`.

- `GET /admin/projects/view`
  - Paskirtis: V3 projects view model (items su next_best_action, attention_flags, stuck_reason, last_activity, client_masked, cursor, as_of, view_version).
  - Auth: `ADMIN`.
  - Query: `status`, `attention_only` (bool, default false), `limit`, `cursor`, `as_of` (ISO, for cursor consistency).
  - Cursor/as_of mismatch -> 400.
  - LOCK 1.1: atskiras nuo GET /admin/projects.

- `GET /admin/projects/mini-triage`
  - Paskirtis: V3 mini triage korteles su primary_action (label, action_key, payload).
  - Auth: `ADMIN`.
  - Query: `limit` (default 20).
  - LOCK 1.6.

- `POST /transition-status`
  - Paskirtis: vienintelis legalus statusu perjungimo kelias.
  - Auth: pagal RBAC matrica (konstitucija).
  - Validacija (payments-first):
    - `DRAFT -> PAID` leidziama tik jei DB yra `payments` faktas:
      - `DEPOSIT`, `SUCCEEDED`, `provider in ('manual','stripe')`, ir
      - arba `amount>0` (realus inasas), arba `amount=0` + `payment_method='WAIVED'` (admin atidejo inasa).

- `POST /projects/{project_id}/payments/manual`
  - Paskirtis: uzregistruoti manual mokejimo fakta (`provider='manual'`, `status='SUCCEEDED'`).
  - Auth: `ADMIN`.
  - Feature flag: `ENABLE_MANUAL_PAYMENTS` (kitu atveju `404`).
  - Idempotencija: `(provider='manual', provider_event_id)` – pakartojus grazina 200 ir `idempotent=true`.
  - Pastaba: endpointas pats nekeicia `projects.status` (statusas keiciamas tik per `transition-status`).

- `POST /admin/projects/{project_id}/payments/deposit-waive`
  - Paskirtis: atideti pradini inasa (pasitikime klientu) – uzregistruoja `DEPOSIT` su `amount=0` ir `payment_method='WAIVED'`.
  - Auth: `ADMIN`.
  - Feature flag: `ENABLE_MANUAL_PAYMENTS` (kitu atveju `404`).
  - Validacija: leidziama tik `DRAFT` projektams.
  - Idempotencija: `(provider='manual', provider_event_id)` – pakartojus grazina 200 ir `idempotent=true`.

- `POST /admin/projects/{project_id}/payment-link`
  - Paskirtis: sukurti Stripe Checkout nuoroda (DEPOSIT arba FINAL).
  - Auth: `ADMIN`.
  - Feature flag: `ENABLE_STRIPE` (kitu atveju `404`).

- `POST /upload-evidence`
  - Paskirtis: ikelti evidence (nuotrauka) i projekta.
  - Auth: reikia (role priklauso nuo implementacijos: tipiskai `CLIENT`/`EXPERT`/`SUBCONTRACTOR`/`ADMIN`).

- `POST /certify-project`
  - Paskirtis: eksperto sertifikavimas (checklist + >=3 foto).
  - Auth: `EXPERT` (arba `ADMIN`).

- `GET /projects/{project_id}/certificate`
  - Paskirtis: sugeneruoti PDF sertifikata (CERTIFIED/ACTIVE).
  - Auth: reikia (prieiga kaip `GET /projects/{id}`).

- `POST /projects/{project_id}/marketing-consent`
  - Paskirtis: uzfiksuoti marketing consent.
  - Auth: reikia (tipiskai `CLIENT`, `ADMIN`).

- `POST /evidences/{evidence_id}/approve-for-web`
  - Paskirtis: patvirtinti evidence rodymui web galerijoje.
  - Auth: `EXPERT` arba `ADMIN`.

- `GET /gallery`
  - Paskirtis: viesas galerijos feed (tik `show_on_web=true`).
  - Auth: nereikia (public).
  - Feature flag: jei galerija gate'inama – ziureti tech doc (marketing modulis).

- `GET /audit-logs`
  - Paskirtis: audito logu perziura su filtrais ir cursor pagination.
  - Auth: `ADMIN` (pilnai); `EXPERT`/`SUBCONTRACTOR` (tik savo priskirtu projektu audit).

- `GET /audit-logs/export`
  - Paskirtis: audito logu eksportas i CSV (stream).
  - Auth: `ADMIN`.

- `GET /admin/token`
  - Paskirtis: techninis endpointas admin JWT sugeneravimui dev/staging.
  - Auth: nereikia, bet turi buti uzdarytas per config (ip allowlist / flag).

### 2.1.1 Admin Dashboard (V3.3, `backend/app/api/v1/admin_dashboard.py`)

- `GET /admin/dashboard`
  - Paskirtis: dashboard view — hero stats, triage kortelės, ai_summary (jei įjungtas), customers_preview.
  - Auth: `ADMIN`.
  - Response: `hero`, `triage`, `ai_summary`, `customers_preview`.

- `GET /admin/dashboard/sse`
  - Paskirtis: SSE stream triage atnaujinimams (5s interval).
  - Auth: query `token=` (admin JWT).
  - Max jungtys: `DASHBOARD_SSE_MAX_CONNECTIONS` (default 5).
  - Feature flags: `ENABLE_AI_SUMMARY` (ai_summary pill), `DASHBOARD_SSE_MAX_CONNECTIONS`.

- `GET /admin/projects/{project_id}/client-token`
  - Paskirtis: sugeneruoti CLIENT token konkretaus projekto klientui.
  - Auth: `ADMIN`.

- `GET /admin/users/{user_id}/contractor-token`
  - Paskirtis: sugeneruoti rangovo token.
  - Auth: `ADMIN`.

- `GET /admin/users/{user_id}/expert-token`
  - Paskirtis: sugeneruoti eksperto token.
  - Auth: `ADMIN`.

- `GET /admin/margins`
  - Paskirtis: marzu lentele.
  - Auth: `ADMIN`.

- `POST /admin/margins`
  - Paskirtis: sukurti nauja marzos irasa.
  - Auth: `ADMIN`.

- `POST /admin/projects/{project_id}/assign-contractor`
  - Paskirtis: priskirti rangova projektui.
  - Auth: `ADMIN`.

- `POST /admin/projects/{project_id}/assign-expert`
  - Paskirtis: priskirti eksperta projektui.
  - Auth: `ADMIN`.

- `POST /admin/projects/{project_id}/seed-cert-photos`
  - Paskirtis: techninis seed/repair endpointas sertifikavimo nuotraukoms (dev).
  - Auth: `ADMIN`.

- `POST /webhook/stripe`
  - Paskirtis: Stripe webhook (payments faktai, idempotencija pagal Stripe event).
  - Auth: nereikia (vietoje to – Stripe signature verification).
  - Feature flag: `ENABLE_STRIPE`.

- `POST /webhook/twilio`
  - Paskirtis: Twilio SMS webhook (CERTIFIED -> ACTIVE tik po "TAIP <KODAS>") — legacy kanalas, V2.3 default yra email.
  - Auth: nereikia (vietoje to – Twilio signature verification).
  - Feature flag: `ENABLE_TWILIO`.

### 2.2 Assistant (`backend/app/api/v1/assistant.py`)

- `POST /call-requests`
  - Paskirtis: vieša callback uzklausa (call assistant).
  - Auth: nereikia (public).
  - Feature flag: `ENABLE_CALL_ASSISTANT` (kitu atveju `404`).
  - Rate limit: max 10/min per IP (429).

- `GET /admin/call-requests`
  - Paskirtis: call-requests sarasas. V3: stats.new_count.
  - Auth: `ADMIN`.
  - Feature flag: `ENABLE_CALL_ASSISTANT` (kitu atveju `404`).

- `PATCH /admin/call-requests/{call_request_id}`
  - Paskirtis: atnaujinti call-request status/notes/preferred_time.
  - Auth: `ADMIN`.
  - Feature flag: `ENABLE_CALL_ASSISTANT` (kitu atveju `404`).

- `GET /admin/appointments`
  - Paskirtis: legacy/admin appointments sarasas (ne Schedule Engine). V3: stats.pending_schedule_count (HELD).
  - Auth: `ADMIN`.
  - Feature flag: `ENABLE_CALENDAR` (kitu atveju `404`).

- `GET /admin/appointments/mini-triage`
  - Paskirtis: V3 mini triage (HELD) su primary_action. LOCK 1.9.
  - Auth: `ADMIN`.

- `POST /admin/appointments/{appointment_id}/confirm-hold`
  - Paskirtis: V3 action – patvirtinti HELD susitikimą. LOCK 1.7.
  - Auth: `ADMIN`.

- `POST /admin/appointments`
  - Paskirtis: sukurti appointment (legacy/admin).
  - Auth: `ADMIN`.
  - Feature flag: `ENABLE_CALENDAR` (kitu atveju `404`).

- `PATCH /admin/appointments/{appointment_id}`
  - Paskirtis: atnaujinti appointment (legacy/admin).
  - Auth: `ADMIN`.
  - Feature flag: `ENABLE_CALENDAR` (kitu atveju `404`).

### 2.3 Schedule Engine (`backend/app/api/v1/schedule.py`)

Visi zemiau esantys endpointai:
- Auth: `SUBCONTRACTOR` arba `ADMIN` (kaip nurodyta konkreciai).
- Feature flag: `ENABLE_SCHEDULE_ENGINE` (kitu atveju `404`).

- `POST /admin/schedule/holds`
  - Paskirtis: sukurti `HELD` rezervacija + `conversation_lock`.
  - Auth: `SUBCONTRACTOR`, `ADMIN`.
  - Konfliktai: `409` jei slot uzimtas (no-overlap) arba conversation turi aktyvu lock.

- `POST /admin/schedule/holds/confirm`
  - Paskirtis: `HELD -> CONFIRMED` (lock_level=1).
  - Auth: `SUBCONTRACTOR`, `ADMIN`.
  - Konfliktai: `409` jei hold pasibaiges arba appointment pasikeites.

- `POST /admin/schedule/holds/cancel`
  - Paskirtis: atsaukti `HELD` rezervacija.
  - Auth: `SUBCONTRACTOR`, `ADMIN`.

- `POST /admin/schedule/holds/expire`
  - Paskirtis: techninis expire endpointas (HELD expired -> CANCELLED).
  - Auth: `ADMIN`.

- `POST /admin/schedule/daily-approve`
  - Paskirtis: uzdeti `lock_level=2` (DAY) visiems pasirinktos dienos `CONFIRMED` vizitams.
  - Auth: `SUBCONTRACTOR`, `ADMIN`.
  - Audit: `DAILY_BATCH_APPROVED` + `APPOINTMENT_LOCK_LEVEL_CHANGED`.

- `POST /admin/schedule/reschedule/preview`
  - Paskirtis: sugeneruoti RESCHEDULE pasiulyma (be mutaciju).
  - Auth: `SUBCONTRACTOR`, `ADMIN`.

- `POST /admin/schedule/reschedule/confirm`
  - Paskirtis: atomiskai pritaikyti RESCHEDULE (`CANCEL + CREATE`) pagal preview/hash + row_version.
  - Auth: `SUBCONTRACTOR`, `ADMIN` (lock taisykles taikomos pagal lock_level).
  - Audit: `SCHEDULE_RESCHEDULED`, `APPOINTMENT_CANCELLED`, `APPOINTMENT_CONFIRMED` su `metadata.reason/comment`.

### 2.4 Webhooks (Voice/Chat)

- `POST /webhook/twilio/voice` (`backend/app/api/v1/twilio_voice.py`)
  - Paskirtis: Twilio Voice webhook MVP (pasiulo laika su `HELD` + patvirtinimas/atsaukimas).
  - Auth: nereikia (vietoje to – Twilio signature verification arba `ALLOW_INSECURE_WEBHOOKS` dev).

- `POST /webhook/chat/events` (`backend/app/api/v1/chat_webhook.py`)
  - Paskirtis: chat integracijos webhook (minimalus pasiulymo + hold confirm/cancel srautas).
  - Auth: pagal integracija (rekomenduojama: HMAC signature arba allowlist).

### 2.5 Email Intake — Unified Client Card (`backend/app/api/v1/intake.py`)

Visi admin endpointai:
- Auth: `ADMIN`.
- Feature flag: `ENABLE_EMAIL_INTAKE` (kitu atveju `404`).

- `GET /admin/intake/{call_request_id}/state`
  - Paskirtis: gauti intake busena (anketa, workflow, aktyvus pasiulymas, istorija).
  - Response: `IntakeStateResponse` (questionnaire, workflow, active_offer, offer_history, questionnaire_complete).

- `PATCH /admin/intake/{call_request_id}/questionnaire`
  - Paskirtis: atnaujinti anketos laukus (email, address, service_type, phone, whatsapp_consent, notes, urgency).
  - Request: `IntakeQuestionnaireUpdate` + `expected_row_version` (optimistic locking).
  - Side effects: jei anketa uzpildyta — auto-prepare (ieskomas artimiausias laisvas slot'as).
  - Audit: `INTAKE_UPDATED`.

- `POST /admin/intake/{call_request_id}/prepare-offer`
  - Paskirtis: peržiureti geriausią laisva slot'a (be mutaciju i appointments).
  - Request: `PrepareOfferRequest` (kind, expected_row_version).
  - Response: `PrepareOfferResponse` (slot_start, slot_end, resource_id, kind, phase).

- `POST /admin/intake/{call_request_id}/send-offer`
  - Paskirtis: sukurti HELD appointment + enqueue email su .ics kvietimu.
  - Response: `SendOfferResponse` (appointment_id, hold_expires_at, attempt_no, phase).
  - Side effects: sukuria `Appointment(status='HELD')`, enqueue email i notification_outbox, optional WhatsApp ping.
  - Audit: `OFFER_SENT`.
  - Hold trukme: `EMAIL_HOLD_DURATION_MINUTES` (default 30 min).
  - Max bandymu: `EMAIL_OFFER_MAX_ATTEMPTS` (default 5).

Viesi endpointai (be auth):

- `GET /public/offer/{token}`
  - Paskirtis: viesas pasiulymo perziura (klientas atidaro is email nuorodos).
  - Response: `PublicOfferView` (slot_start, slot_end, address, kind, status).
  - Token lookup: JSONB `intake_state.active_offer.token_hash` (SHA-256).

- `POST /public/offer/{token}/respond`
  - Paskirtis: klientas priima arba atsisako pasiulymo.
  - Request: `OfferResponseRequest` (action: "accept"|"reject", suggest_text).
  - Side effects:
    - accept: `HELD → CONFIRMED`, phase=`INSPECTION_SCHEDULED`. Audit: `OFFER_ACCEPTED`.
    - reject: `HELD → CANCELLED`, auto-prepare naujas slot'as. Audit: `OFFER_REJECTED`.
  - Response: `OfferResponseResult` (status, message, next_slot_start/end jei reject).

- `POST /public/activations/{token}/confirm`
  - Pastaba: kanoninis endpointas yra `POST /public/confirm-payment/{token}` (`backend/app/api/v1/projects.py`). Sis `/public/activations/...` yra legacy alias (`backend/app/api/v1/intake.py`).
  - Paskirtis: CERTIFIED → ACTIVE per email patvirtinima (alternatyva SMS per Twilio).
  - Lookup: `client_confirmations.token_hash` (SHA-256).
  - Validacija: status=PENDING, nepasibaiges, projektas CERTIFIED.
  - Actor: `SYSTEM_EMAIL`.
  - Audit: `STATUS_CHANGED` (CERTIFIED→ACTIVE) su `channel` ir `confirmation_id` metadata.

### 2.6 Finance Module V2.3 (`backend/app/api/v1/finance.py`)

- `POST /projects/{project_id}/quick-payment-and-transition`
  - Paskirtis: quick-payment su automatine statuso tranzicija (DEPOSIT->PAID, FINAL->email confirmation).
  - Auth: `ADMIN`.
  - Feature flag: `ENABLE_FINANCE_LEDGER` (kitu atveju `404`).
  - Idempotencija: `UNIQUE(provider, provider_event_id)` — identiski parametrai -> 200, skirtingi -> 409.
  - Response schema: `QuickPaymentResponse` su `email_queued` (V2.3, buvo `sms_queued`).
  - Side effects: FINAL + CERTIFIED + `ENABLE_EMAIL_INTAKE=true` + kliento email -> enqueue email confirmation.

- `GET /admin/finance/view`
  - Paskirtis: V3 finance view model (mini_triage, manual_payments_count_7d, ai_summary).
  - Auth: `ADMIN`.
  - Feature flag: `ENABLE_FINANCE_LEDGER` (kitu atveju `404`).
  - V3 Diena 4.

- `GET /admin/finance/mini-triage`
  - Paskirtis: V3 mini triage laukiantys mokėjimai (DRAFT be depozito, CERTIFIED be final).
  - Auth: `ADMIN`.
  - Query: `limit` (default 20).
  - LOCK 1.6 pattern.
  - V3 Diena 4.

- `GET /admin/finance/ledger`
  - Paskirtis: finance ledger (mokejimu sarasas su filtrais).
  - Auth: `ADMIN`.
  - Feature flag: `ENABLE_FINANCE_LEDGER` (kitu atveju `404`).

- `POST /admin/finance/extract`
  - Paskirtis: AI dokumento iskvietimas (proposal-only, niekada auto-confirm).
  - Auth: `ADMIN`.
  - Feature flag: `ENABLE_FINANCE_LEDGER` (kitu atveju `404`).
  - Pastaba: AI rezultatas saugomas `payments.ai_extracted_data` admin review'ui.

- `GET /admin/finance/metrics`
  - Paskirtis: SSE (Server-Sent Events) realaus laiko finance metrikos.
  - Auth: `ADMIN`.
  - Feature flag: `ENABLE_FINANCE_METRICS` (kitu atveju `404`).
  - Response: `text/event-stream` (SSE), kas 5s atnaujinimas.
  - Metrikos: `daily_volume`, `manual_ratio`, `avg_attempts`, `reject_rate`, `avg_confirm_time_minutes`.
  - Saugikliai: max concurrent connections (`FINANCE_METRICS_MAX_SSE_CONNECTIONS`, default 5), be PII.
  - Rate limit: 429 jei per daug aktyviu SSE jungciu.

- `POST /public/confirm-payment/{token}`
  - Paskirtis: viesas email patvirtinimo endpointas (CERTIFIED -> ACTIVE).
  - Auth: nereikia (token yra kredencialas).
  - Feature flag: `ENABLE_EMAIL_INTAKE` (kitu atveju `404`).
  - Lookup: `client_confirmations.token_hash` (SHA-256).
  - Validacija: status=PENDING, nepasibaiges, projektas CERTIFIED, FINAL payment egzistuoja.
  - Actor: `SYSTEM_EMAIL`.
  - Response: `{"success": true, "project_id": "...", "new_status": "ACTIVE"}`.
  - Idempotencija: jau patvirtintas -> `{"success": true, "already_confirmed": true}`.

### 2.7 Notification Outbox Kanalai

Notification outbox (`notification_outbox` lentele) dabar palaiko 3 kanalus:
- `sms` — legacy Twilio SMS (per `sms_service.send_sms()`).
- `email` — SMTP email su optional .ics kalendoriaus kvietimu (per `outbox_channel_send()`).
- `whatsapp_ping` — WhatsApp ping (per Twilio, jei `ENABLE_WHATSAPP_PING=true`).

### 2.8 Client UI V3 (`backend/app/api/v1/client_views.py`)

Visi endpointai: Auth `CLIENT` (JWT). Prieigos klaidos: **404** (ne 403). Pilna specifikacija: `backend/docs/CLIENT_UI_V3.md`.

- `GET /client/dashboard`
  - Paskirtis: vienas view modelis kliento dashboard (action_required, projects, upsell_cards, feature_flags). Be PII.

- `GET /client/projects/{project_id}/view`
  - Paskirtis: projekto detalės view (status, next_step_text, primary_action, secondary_actions, documents, timeline, payments_summary, addons_allowed). 404 jei klientas neturi prieigos.

- `GET /client/estimate/rules`
  - Paskirtis: kainodaros taisyklės (rules_version, base_rates, addons, disclaimer, confidence_messages). FE nekoduoja kainų.

- `POST /client/estimate/analyze`
  - Paskirtis: analizuoti plotą/nuotraukas (ai_complexity, base_range, confidence_bucket). Optional: `ENABLE_VISION_AI`.

- `POST /client/estimate/price`
  - Paskirtis: skaičiuoti total_range iš base_range + addons_selected. **409** su `expected_rules_version` jei rules_version pasenęs.

- `POST /client/estimate/submit`
  - Paskirtis: sukurti Project DRAFT, `client_info.estimate`, `quote_pending=true`. **409** jei rules_version pasenęs.

- `GET /client/services/catalog`
  - Paskirtis: deterministinis paslaugų katalogas (3–6 kortelių), query `context=pre_active|active`, `catalog_version`.

- `POST /client/services/request`
  - Paskirtis: sukurti įrašą `service_requests`. PAID+ projektas = visada atskiras request (scope creep saugiklis).

- `POST /client/actions/pay-deposit`
- `POST /client/actions/sign-contract`
- `POST /client/actions/pay-final`
- `POST /client/actions/confirm-acceptance`
- `POST /client/actions/order-service`
  - Paskirtis: kliento veiksmai (UI niekada nekviečia `transition-status`). Body: `{ "project_id": "uuid" }`. Atsakas: `action`, `message` arba `path`.

---

## 3) Admin UI V3 endpointai

Admin UI V3 turi du papildomus plonus routerius:
- `backend/app/api/v1/admin_customers.py`
- `backend/app/api/v1/admin_project_details.py`

### 3.1 Admin Customers (`backend/app/api/v1/admin_customers.py`)

- `GET /admin/customers`
  - Paskirtis: klientu sarasas, agreguotas is projektu pagal derived `client_key`.
  - Auth: `ADMIN`.
  - PII: serveris grazina tik maskuotus kontaktus.
  - Default: `attention_only=true` (Inbox Zero).
  - Pagination: `limit`, `cursor`, `as_of` (snapshot).

- `GET /admin/customers/stats`
  - Paskirtis: dashboard helperis (unikaliu klientu skaicius per 12 men.).
  - Auth: `ADMIN`.

- `GET /admin/customers/{client_key}/profile`
  - Paskirtis: pilnas kliento profilio view model (UI tik renderina).
  - Auth: `ADMIN`.
  - Feature flags: `feature_flags.*` grizta response'e (UI sprendimams).

### 3.2 Admin Project Details (`backend/app/api/v1/admin_project_details.py`)

- `GET /admin/projects/{project_id}/payments`
  - Paskirtis: projekto mokejimu sarasas (payments tab).
  - Auth: `ADMIN`.

- `GET /admin/projects/{project_id}/confirmations`
  - Paskirtis: projekto kliento patvirtinimu sarasas (confirmations tab).
  - Auth: `ADMIN`.
  - Kontraktas: `can_resend`, `resends_remaining`, `reset_at`.

- `POST /admin/projects/{project_id}/confirmations/resend`
  - Paskirtis: persiusti patvirtinima (email arba sms).
  - Auth: `ADMIN`.
  - Rate limit: max 3 per 24h (grizta `remaining`, `reset_at`).

- `GET /admin/projects/{project_id}/notifications`
  - Paskirtis: outbox irasai susieti su projektu (communications tab).
  - Auth: `ADMIN`.
  - Kontraktas: `can_retry`, `retries_remaining`, `reset_at`.

- `POST /admin/notifications/{notification_id}/retry`
  - Paskirtis: rankinis FAILED outbox iraso retry.
  - Auth: `ADMIN`.
  - Rate limit: max 3 per 24h (grizta `remaining`, `reset_at`).

### 3.3 Admin override aktyvacija (reason privalomas)

- `POST /admin/projects/{project_id}/admin-confirm`
  - Paskirtis: admin-only override (CERTIFIED -> ACTIVE), bypass'inant email/SMS flow.
  - Auth: `ADMIN`.
  - Request body: `{ "reason": "..." }` (privaloma).

### 3.4 Admin Global Search (`backend/app/api/v1/admin_search.py`) — V3 Diena 5–6

- `GET /admin/search?q=`
  - Paskirtis: globali paieška — projektai (ID, status), skambučių užklausos (ID). Max 50.
  - Auth: `ADMIN`.
  - LOCK 1.4: loguose loginti tik `q` ilgį (ne PII). 404 jei nėra prieigos.
  - Response: `items` (type, id, label, href).

### 3.5 AI Admin (`backend/app/api/v1/ai.py`) — V3 Diena 4

- `GET /admin/ai/view`
  - Paskirtis: V3 AI view model (low_confidence_count, attention_items, ai_summary).
  - Auth: `ADMIN`.
  - Response: `low_confidence_count` (pastarų 24h), `attention_items` (confidence < 0.5), `ai_summary` (jei ENABLE_AI_SUMMARY).
  - V3 Diena 4.

- `POST /admin/ai/parse-intent`
  - Paskirtis: Klasifikuoti skambintojo ketinimą per AI (intent parsing).
  - Auth: `ADMIN`.
  - Feature flag: `ENABLE_AI_INTENT` (kitu atveju `404`).
  - Request: `ParseIntentRequest` (text, override_provider?, override_model?).
  - Response: `ParseIntentResponse` (intent, confidence, params, provider, model, attempts, latency_ms).

- `POST /admin/ai/extract-conversation`
  - Paskirtis: Ištraukti kliento kontaktinius duomenis iš pokalbio teksto arba skambučio transkripcijos per AI.
  - Auth: `ADMIN`.
  - Feature flag: `ENABLE_AI_CONVERSATION_EXTRACT` (kitu atveju `404`).
  - Request: `ExtractConversationRequest` (text, call_request_id?, auto_apply=true).
  - Response: `ExtractConversationResponse` (fields: {field_name: {value, confidence, applied}}, provider, model, attempts, latency_ms, applied_count).
  - Modelis: Claude Haiku 4.5 (default). Budget-based retry (8s).
  - Šalutinis efektas: su `auto_apply=true` + `call_request_id`, aukšto confidence laukai automatiškai įrašomi į `intake_state.questionnaire` per `merge_ai_suggestions()`.
  - Ištraukiami laukai: client_name, phone, email, address, service_type, urgency, area_m2.
