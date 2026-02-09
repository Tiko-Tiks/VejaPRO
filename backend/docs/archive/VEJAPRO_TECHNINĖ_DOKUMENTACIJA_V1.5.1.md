# VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.1 (Patch)

Data: 2026-02-07  
Statusas: Patch (papildo `VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md`)

Sis patch'as atnaujina V1.5, nekeisdamas bazines architekturos principu, ir suderina sistema su:
- `VEJAPRO_KONSTITUCIJA_V1.4.md` (payments-first manual, Stripe optional).

## 1. Feature flags (prideta)

- `ENABLE_MANUAL_PAYMENTS=true`
- `ENABLE_STRIPE=false`
- `ENABLE_TWILIO=true`
- `RATE_LIMIT_API_ENABLED=true` (rekomenduojama)
- `SUPABASE_JWT_AUDIENCE=authenticated` (rekomenduojama)
- `EXPOSE_ERROR_DETAILS=false` (rekomenduojama produkcijai)

Pastabos:
- `ENABLE_STRIPE=false` reiskia, kad Stripe admin ir webhook endpointai gali buti isjungti, bet schema ir kodas palaiko Stripe ateiciai.
- Twilio paliekamas kaip aktyvavimo patvirtinimo kanalas (kol kas).
- `RATE_LIMIT_API_ENABLED=true` ijungia IP rate limit visiems `/api/v1/*` endpointams (isskyrus webhook'us).
- `SUPABASE_JWT_AUDIENCE` naudojamas JWT `aud` validacijai ir vidiniu JWT generavimui.
- `EXPOSE_ERROR_DETAILS=false` slepia vidines 5xx klaidu detales klientui (vis tiek loguojama serveryje).

## 2. DB schema - payments (papildymai)

Esama `payments` lentele papildoma laukais, kad butu galima fiksuoti "kas realiai gavo pinigus" ir manual konteksta.

Papildyti laukai:
- `payment_method VARCHAR(32) NULL` (pvz. `CASH`, `BANK_TRANSFER`, `STRIPE`)
- `received_at TIMESTAMPTZ NULL`
- `collected_by UUID NULL REFERENCES users(id)`
- `collection_context VARCHAR(32) NULL` (pvz. `ON_SITE_AFTER_WORK`, `ON_SITE_BEFORE_WORK`, `REMOTE`, `OFFICE`)
- `receipt_no VARCHAR(64) NULL`
- `proof_url TEXT NULL`
- `is_manual_confirmed BOOLEAN NOT NULL DEFAULT FALSE`
- `confirmed_by UUID NULL REFERENCES users(id)`
- `confirmed_at TIMESTAMPTZ NULL`

V2.3 papildymai:
- `ai_extracted_data JSONB NULL` — AI iskviecimo proposal (naudojamas admin review, niekada auto-confirm)
- `UNIQUE(provider, provider_event_id)` — idempotencijos index (globalus)

Idempotencija:
- manual: `(provider='manual', provider_event_id)` (unikalus) remiasi esamu unikaliu indeksu `idx_payments_event (provider, provider_event_id)`.
- papildomai (neprivaloma): `uniq_payments_manual_receipt` ant `(provider, receipt_no)` tik kai `provider='manual' AND receipt_no IS NOT NULL`.

## 3. RBAC perejimu matrica (pakeista tik DRAFT -> PAID)

- `DRAFT -> PAID`: `SUBCONTRACTOR` arba `ADMIN`, jei DB yra `payments` irasas:
  - `payment_type='DEPOSIT'`
  - `status='SUCCEEDED'`
  - `provider IN ('manual','stripe')`
  - arba `amount > 0` (realus įnašas)
  - arba `amount = 0` ir `payment_method='WAIVED'` (ADMIN atidėjo įnašą, pasitikime klientu)
- Kiti perejimai: kaip V1.5 / V1.3.

## 4. Naujas endpointas: manual mokejimo faktas

`POST /api/v1/projects/{project_id}/payments/manual`

Kas gali:
- `ADMIN`.

Request (pavyzdys):
```json
{
  "payment_type": "DEPOSIT",
  "amount": 300.00,
  "currency": "EUR",
  "payment_method": "CASH",
  "provider_event_id": "CASH-2026-000123",
  "receipt_no": "CASH-2026-000123",
  "received_at": "2026-02-07T15:40:00Z",
  "collection_context": "ON_SITE_BEFORE_WORK",
  "proof_url": "https://.../receipt.jpg",
  "notes": "Paeme ekspertas vietoje"
}
```

Backend taisykles:
- iraso i `payments` su:
  - `provider='manual'`
  - `status='SUCCEEDED'`
- privaloma idempotencija per `provider_event_id`:
  - pakartotas `provider_event_id` negali sukurti antro iraso (endpoint turi buti idempotentiskas).
- privalomas audit:
  - `PAYMENT_RECORDED_MANUAL` (entity_type=`payment`).
- endpointas nekeicia `projects.status`.

## 4.1 Naujas endpointas: įnašo atidėjimas (pasitikime klientu)

Kai norime laikinai dirbti be pradinio įnašo (pvz. patikimas klientas), admin gali užregistruoti "waived" įnašą kaip `DEPOSIT` faktą su `amount=0`.

`POST /api/v1/admin/projects/{project_id}/payments/deposit-waive`

Request (pavyzdys):
```json
{
  "provider_event_id": "WAIVE-2026-000001",
  "currency": "EUR",
  "notes": "Pasitikime klientu"
}
```

Taisyklės:
- leidžiama tik `DRAFT` projektams,
- sukuria `payments` įrašą:
  - `provider='manual'`
  - `payment_type='DEPOSIT'`
  - `amount=0`
  - `payment_method='WAIVED'`
  - `is_manual_confirmed=true`
- audit:
  - `PAYMENT_RECORDED_MANUAL` (entity_type=`payment`)
  - `DEPOSIT_WAIVED` (entity_type=`project`)

## 5. /transition-status validacijos pakeitimas (DRAFT -> PAID)

Kai `new_status='PAID'` ir projektas `DRAFT`, backend privalo rasti `DEPOSIT` mokejima (manual arba stripe). Jei neranda - `400`.

## 6. FINAL mokejimas (manual/stripe) ir patvirtinimo inicijavimas (V2.3 — email-first)

Kai uzregistruojamas `payment_type='FINAL'` (manual arba stripe) ir projektas yra `CERTIFIED`:
- backend sukuria patvirtinimo request (`client_confirmations` lentelė, `PENDING`, `channel='email'`) ir enqueue email per `notification_outbox`,
- statuso nekeicia; statusa pakeis tik:
  - `POST /api/v1/public/confirm-payment/{token}` (email, `SYSTEM_EMAIL`) — **default V2.3**, arba
  - Twilio webhook po "TAIP <KODAS>" (SMS, `SYSTEM_TWILIO`) — legacy.

CERTIFIED -> ACTIVE reikalauja ABU salygu:
- `client_confirmations` su `status='CONFIRMED'`
- `payments` su `payment_type='FINAL'`, `status='SUCCEEDED'`

Svarbu:
- `client_confirmations` lentelė palaiko kanalus: `sms`, `email`, `whatsapp`.
- Email patvirtinimo endpointas (`POST /api/v1/public/confirm-payment/{token}`) naudoja `SYSTEM_EMAIL` aktoriaus tipą.
- Patvirtinimo endpointas tikrina, kad `FINAL` mokejimas yra uzregistruotas (pries aktyvuojant).

## 6.1 RBAC papildymas (V2.2)

- `CERTIFIED -> ACTIVE`: leidžiami aktoriai — `SYSTEM_TWILIO` (SMS) ir `SYSTEM_EMAIL` (email patvirtinimas).
- Naujas sistemos aktoriaus tipas `SYSTEM_EMAIL` pridėtas prie RBAC matricų.

## 7. Minimalus testu planas (privalomas)

- Manual idempotencija:
  - pakartotas `provider_event_id` -> antras irasas nesukuriamas (status 200, `idempotent=true`).
- `DRAFT -> PAID`:
  - be `DEPOSIT` payment -> 400
  - su manual `DEPOSIT` (`SUCCEEDED`) -> OK
  - su `DEPOSIT` waived (`amount=0`, `payment_method='WAIVED'`) -> OK
- `FINAL + CERTIFIED`:
  - manual `FINAL` sukuria email confirmation request (PENDING, `channel='email'`)
  - be patvirtinimo statusas lieka `CERTIFIED`
  - po email token patvirtinimo (`POST /public/confirm-payment/{token}`) statusas tampa `ACTIVE` (`SYSTEM_EMAIL`)
  - legacy SMS: po "TAIP <KODAS>" statusas tampa `ACTIVE` (`SYSTEM_TWILIO`)
- V2.3 email patvirtinimas:
  - valid token -> 200, `success=true`
  - invalid token -> 404
  - already confirmed -> 200, `already_confirmed=true`
  - email intake disabled -> 404
