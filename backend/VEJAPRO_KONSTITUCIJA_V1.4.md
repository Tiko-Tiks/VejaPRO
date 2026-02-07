# VEJAPRO_KONSTITUCIJA_V1.4 (Payments-first Manual, Stripe optional)

Data: 2026-02-07  
Statusas: Galiojanti korekcija (V1.3 papildymas)

Si redakcija pakeicia ankstesne `VEJAPRO_KONSTITUCIJA_V1.3.md` tiek, kiek nurodyta zemiau. Konflikto atveju galioja V1.4.

## 0.1 Statusai (aibe nekinta)

Leidziami statusai:
- `DRAFT`
- `PAID`
- `SCHEDULED`
- `PENDING_EXPERT`
- `CERTIFIED`
- `ACTIVE`

## 0.2 Statusas = darbo eiga (nekinta)

Statusas yra darbo eigos asis. Mokejimo kanalai nera statusai.

## 0.3 Vienintelis legalus statusu keitimo kelias (nekinta)

Statusas keiciamas tik per:
- `POST /api/v1/transition-status`

Taisykles:
- forward-only,
- su audit log.

## 0.4 Mokejimu doktrina (nauja)

Vienintele tiesa apie gautus pinigus yra `payments` faktai:
- `provider='manual'` arba `provider='stripe'`.

`stripe` yra optional kanalas. `manual` (CASH/BANK) yra default.

`payments` fakta iveda tas, kas realiai gavo pinigus:
- `SUBCONTRACTOR`, `EXPERT` arba `ADMIN`.

Kiekvienas mokejimo faktas privalo buti:
- idempotentiskas,
- audituojamas.

## 0.5 DRAFT -> PAID (pakeista)

`DRAFT -> PAID` leidziama tik jei egzistuoja `DEPOSIT` mokejimo faktas `payments` lenteleje:
- `payment_type='DEPOSIT'`
- `status='SUCCEEDED'`
- `amount > 0`
- `provider IN ('manual','stripe')`

Perejima inicijuoja:
- `SUBCONTRACTOR` arba `ADMIN` per `POST /api/v1/transition-status`.

Backend privalo validuoti, kad mokejimo faktas egzistuoja. Ankstesne taisykle "tik SYSTEM_STRIPE" panaikinama.

## 0.6 CERTIFIED -> ACTIVE (nekinta, bet patikslinta)

`CERTIFIED -> ACTIVE` vykdomas tik po kliento SMS patvirtinimo per Twilio webhook:
- `SYSTEM_TWILIO`

`FINAL` mokejimo faktas (`payment_type='FINAL'`, `provider manual/stripe`) yra privaloma salyga SMS patvirtinimo grandinei:
- SMS request galima inicijuoti tik jei `FINAL` apmokejimas fiksuotas,
- pats `FINAL` statuso nekeicia.

## 0.7 Aktoriai (aibe nekinta)

Leidziami `actor_type`:
- `SYSTEM_STRIPE`
- `SYSTEM_TWILIO`
- `CLIENT`
- `SUBCONTRACTOR`
- `EXPERT`
- `ADMIN`

Jokiu nauju actor_type.

## 0.8 Idempotencija (pakeista mokejimams)

Manual mokejimai:
- idempotencija per `(provider='manual', provider_event_id)` (unikalus globaliai).

Stripe mokejimai:
- idempotencija per Stripe event/payment identifikatorius (kaip iki siol).

## 0.9 Kanoniniai endpointai (papildyta)

Papildomas kanoninis endpointas mokejimo faktu registravimui:
- `POST /api/v1/projects/{project_id}/payments/manual`

Kiti kanoniniai endpointai lieka (iskaitant webhook'us).

