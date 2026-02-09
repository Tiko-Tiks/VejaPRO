# VEJAPRO_KONSTITUCIJA_V1.4 (Payments-first Manual, Stripe optional)

Data: 2026-02-09
Statusas: Galiojanti korekcija (V1.3 papildymas + V2.3 email aktyvacija)

Si redakcija pakeicia ankstesne `VEJAPRO_KONSTITUCIJA_V1.3.md` tiek, kiek nurodyta zemiau. Konflikto atveju galioja V1.4.
V2.3 pakeitimai: SMS aktyvacija -> Email token aktyvacija (default), `SYSTEM_EMAIL` aktorius, `client_confirmations` infrastruktura.

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

## 0.6 CERTIFIED -> ACTIVE (V2.3 — email patvirtinimas)

`CERTIFIED -> ACTIVE` vykdomas tik po kliento patvirtinimo per viena is kanalu:
- `SYSTEM_TWILIO` (SMS: klientas atsako "TAIP <KODAS>" per Twilio webhook)
- `SYSTEM_EMAIL` (Email: klientas paspaudzia nuoroda `POST /api/v1/public/confirm-payment/{token}`)

Patvirtinimo infrastruktura: `client_confirmations` lentele, `channel` stulpelis (`email` default, `sms` legacy).

`FINAL` mokejimo faktas (`payment_type='FINAL'`, `provider manual/stripe`) yra privaloma salyga patvirtinimo grandinei:
- patvirtinimo request galima inicijuoti tik jei `FINAL` apmokejimas fiksuotas,
- pats `FINAL` statuso nekeicia.

Aktyvavimai reikalauja ABU salygu:
- `client_confirmations` su `status='CONFIRMED'` (per email arba SMS)
- `payments` su `payment_type='FINAL'`, `status='SUCCEEDED'`

## 0.7 Aktoriai (aibe nekinta)

Leidziami `actor_type`:
- `SYSTEM_STRIPE`
- `SYSTEM_TWILIO`
- `SYSTEM_EMAIL` (V2.3 — email patvirtinimas)
- `CLIENT`
- `SUBCONTRACTOR`
- `EXPERT`
- `ADMIN`

## 0.8 Idempotencija (pakeista mokejimams)

Manual mokejimai:
- idempotencija per `(provider='manual', provider_event_id)` (unikalus globaliai).

Stripe mokejimai:
- idempotencija per Stripe event/payment identifikatorius (kaip iki siol).

## 0.9 Kanoniniai endpointai (papildyta)

Papildomas kanoninis endpointas mokejimo faktu registravimui:
- `POST /api/v1/projects/{project_id}/payments/manual`

Kiti kanoniniai endpointai lieka (iskaitant webhook'us).

