# VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.1 (Patch)

Data: 2026-02-07  
Statusas: Patch (papildo `VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md`)

Sis patch'as atnaujina V1.5, nekeisdamas bazines architekturos principu, ir suderina sistema su:
- `VEJAPRO_KONSTITUCIJA_V1.4.md` (payments-first manual, Stripe optional).

## 1. Feature flags (prideta)

- `ENABLE_MANUAL_PAYMENTS=true`
- `ENABLE_STRIPE=false`
- `ENABLE_TWILIO=true`

Pastabos:
- `ENABLE_STRIPE=false` reiskia, kad Stripe admin ir webhook endpointai gali buti isjungti, bet schema ir kodas palaiko Stripe ateiciai.
- Twilio paliekamas kaip aktyvavimo patvirtinimo kanalas (kol kas).

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

Idempotencija:
- manual: `(provider='manual', provider_event_id)` (unikalus) remiasi esamu unikaliu indeksu `idx_payments_event (provider, provider_event_id)`.
- papildomai (neprivaloma): `uniq_payments_manual_receipt` ant `(provider, receipt_no)` tik kai `provider='manual' AND receipt_no IS NOT NULL`.

## 3. RBAC perejimu matrica (pakeista tik DRAFT -> PAID)

- `DRAFT -> PAID`: `SUBCONTRACTOR` arba `ADMIN`, jei DB yra `payments` irasas:
  - `payment_type='DEPOSIT'`
  - `status='SUCCEEDED'`
  - `provider IN ('manual','stripe')`
  - `amount > 0`
- Kiti perejimai: kaip V1.5 / V1.3.

## 4. Naujas endpointas: manual mokejimo faktas

`POST /api/v1/projects/{project_id}/payments/manual`

Kas gali:
- `SUBCONTRACTOR`, `EXPERT`, `ADMIN`.

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

## 5. /transition-status validacijos pakeitimas (DRAFT -> PAID)

Kai `new_status='PAID'` ir projektas `DRAFT`, backend privalo rasti `DEPOSIT` mokejima (manual arba stripe). Jei neranda - `400`.

## 6. FINAL mokejimas (manual/stripe) ir SMS inicijavimas (nekintant statusui)

Kai uzregistruojamas `payment_type='FINAL'` (manual arba stripe) ir projektas yra `CERTIFIED`:
- backend sukuria SMS patvirtinimo request (`sms_confirmations`, `PENDING`) ir bando issiusti SMS (jei `ENABLE_TWILIO=true`),
- statuso nekeicia; statusa pakeis tik Twilio webhook po "TAIP <KODAS>".

Svarbu:
- Twilio patvirtinimo endpointas tikrina, kad `FINAL` mokejimas yra uzregistruotas (pries aktyvuojant).

## 7. Minimalus testu planas (privalomas)

- Manual idempotencija:
  - pakartotas `provider_event_id` -> antras irasas nesukuriamas (status 200, `idempotent=true`).
- `DRAFT -> PAID`:
  - be `DEPOSIT` payment -> 400
  - su manual `DEPOSIT` (`SUCCEEDED`) -> OK
- `FINAL + CERTIFIED`:
  - manual `FINAL` sukuria SMS request (PENDING)
  - be "TAIP" statusas lieka `CERTIFIED`
  - po "TAIP <KODAS>" statusas tampa `ACTIVE` (`SYSTEM_TWILIO`)

