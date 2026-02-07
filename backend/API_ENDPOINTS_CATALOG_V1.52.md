# VejaPRO API Endpointu Katalogas (V1.52)

Data: 2026-02-07  
Statusas: Gyvas (atitinka esama backend implementacija)  
Pastaba: kanoniniai principai ir statusu valdymas lieka pagal `VEJAPRO_KONSTITUCIJA_V1.3.md` + `VEJAPRO_KONSTITUCIJA_V1.4.md` (payments-first).

## 0) Bendros taisykles

- Visi endpointai turi prefiksa: `/api/v1`.
- Statusai keiciami tik per `POST /api/v1/transition-status` (forward-only) su audit.
- Auth: naudojamas Supabase JWT (HS256). Role imama is `app_metadata.role`.
- RBAC: roles tik kanonines: `CLIENT`, `SUBCONTRACTOR`, `EXPERT`, `ADMIN` (sistemos aktoriai webhooks: `SYSTEM_STRIPE`, `SYSTEM_TWILIO`).
- Feature flags: jei funkcija isjungta, endpointas turi grazinti `404` (ne `403`) ir neskelbti, kad funkcija egzistuoja.

## 1) Feature Flags (gating)

- `ENABLE_SCHEDULE_ENGINE` – Schedule Engine endpointai.
- `ENABLE_CALL_ASSISTANT` – Call assistant public forma ir admin call-requests/admin appointments.
- `ENABLE_CALENDAR` – legacy/admin appointments endpointai (`/admin/appointments`).
- `ENABLE_MANUAL_PAYMENTS` – manual payments endpointas.
- `ENABLE_STRIPE` – Stripe checkout link endpointas ir Stripe webhook logika.
- `ENABLE_TWILIO` – Twilio SMS webhook logika (aktyvavimas) ir (jei naudojama) SMS siuntimas.
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
  - Paskirtis: admin projektu sarasas su filtrais/pagination.
  - Auth: `ADMIN`.

- `POST /transition-status`
  - Paskirtis: vienintelis legalus statusu perjungimo kelias.
  - Auth: pagal RBAC matrica (konstitucija).
  - Validacija (payments-first):
    - `DRAFT -> PAID` leidziama tik jei DB yra `payments` faktas: `DEPOSIT`, `SUCCEEDED`, `amount>0`, `provider in ('manual','stripe')`.

- `POST /projects/{project_id}/payments/manual`
  - Paskirtis: uzregistruoti manual mokejimo fakta (`provider='manual'`, `status='SUCCEEDED'`).
  - Auth: `SUBCONTRACTOR`, `EXPERT`, `ADMIN`.
  - Feature flag: `ENABLE_MANUAL_PAYMENTS` (kitu atveju `404`).
  - Idempotencija: `(provider='manual', provider_event_id)` – pakartojus grazina 200 ir `idempotent=true`.
  - Pastaba: endpointas pats nekeicia `projects.status` (statusas keiciamas tik per `transition-status`).

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
  - Auth: `ADMIN`.

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
  - Paskirtis: Twilio SMS webhook (CERTIFIED -> ACTIVE tik po "TAIP <KODAS>").
  - Auth: nereikia (vietoje to – Twilio signature verification).
  - Feature flag: `ENABLE_TWILIO`.

### 2.2 Assistant (`backend/app/api/v1/assistant.py`)

- `POST /call-requests`
  - Paskirtis: vieša callback uzklausa (call assistant).
  - Auth: nereikia (public).
  - Feature flag: `ENABLE_CALL_ASSISTANT` (kitu atveju `404`).
  - Rate limit: max 10/min per IP (429).

- `GET /admin/call-requests`
  - Paskirtis: call-requests sarasas.
  - Auth: `ADMIN`.
  - Feature flag: `ENABLE_CALL_ASSISTANT` (kitu atveju `404`).

- `PATCH /admin/call-requests/{call_request_id}`
  - Paskirtis: atnaujinti call-request status/notes/preferred_time.
  - Auth: `ADMIN`.
  - Feature flag: `ENABLE_CALL_ASSISTANT` (kitu atveju `404`).

- `GET /admin/appointments`
  - Paskirtis: legacy/admin appointments sarasas (ne Schedule Engine).
  - Auth: `ADMIN`.
  - Feature flag: `ENABLE_CALENDAR` (kitu atveju `404`).

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
