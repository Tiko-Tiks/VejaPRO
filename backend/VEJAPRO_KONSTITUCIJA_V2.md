# VEJAPRO KONSTITUCIJA V.2 (2026 m. Konsoliduota Redakcija)

## TURINYS

0. [Korekcijos ir Suderinimai](#0-korekcijos-ir-suderinimai)
1. [Sistemos Stuburas](#1-sistemos-stuburas-core-domain)
2. [Projektu Statusu Ciklas](#2-projektu-statusu-ciklas-forward-only)
3. [Etapiskumas ir Exit Criteria](#3-etapiskumas-ir-exit-criteria)
4. [AI Diegimo ir Teisine Logika](#4-ai-diegimo-ir-teisine-logika)
5. [Technine Uzduotis](#5-technine-uzduotis-api-endpoints)
6. [Eksperto Sertifikavimo Checklist](#6-eksperto-sertifikavimo-checklistas)
7. [Neuzrasytos Taisykles](#7-neuzrasytos-bet-privalomos-taisykles)
8. [Pagrindiniai Principai](#8-principai-kuriu-niekada-nekeiciame)
---


## 0. KOREKCIJOS IR SUDERINIMAI

Si dalis yra kanonine Core Domain specifikacija. Jei randamas konfliktas, galioja si dalis.

1. Statusai (vienintele leidziama aibe): DRAFT, PAID, SCHEDULED, PENDING_EXPERT, CERTIFIED, ACTIVE.
2. Statusas yra darbo eigos asis. Mokejimo kanalai nera statusai.
3. Statusas keiciamas tik per POST /api/v1/transition-status, forward-only. Kiekvienas perejimas privalo sukurti audit log.
4. is_certified privalo atitikti status in (CERTIFIED, ACTIVE) (DB constraint arba triggeris).
5. Marketingo viesinimas tik jei: marketing_consent = true, status >= CERTIFIED, veiksma atlieka EXPERT arba ADMIN.
6. Perejimu matrica: DRAFT->PAID, PAID->SCHEDULED, SCHEDULED->PENDING_EXPERT, PENDING_EXPERT->CERTIFIED, CERTIFIED->ACTIVE. Kiti perejimai = 400.
7. Aktoriai: SYSTEM_STRIPE, SYSTEM_TWILIO, **SYSTEM_EMAIL**, CLIENT, SUBCONTRACTOR, EXPERT, ADMIN. Leidimai:
   - DRAFT->PAID: **SYSTEM_STRIPE, SUBCONTRACTOR arba ADMIN** (reikia DEPOSIT mokejimo fakto)
   - PAID->SCHEDULED: SUBCONTRACTOR arba ADMIN
   - SCHEDULED->PENDING_EXPERT: SUBCONTRACTOR arba ADMIN
   - PENDING_EXPERT->CERTIFIED: EXPERT arba ADMIN (>=3 EXPERT_CERTIFICATION + checklist)
   - CERTIFIED->ACTIVE: **SYSTEM_TWILIO arba SYSTEM_EMAIL** (final mokejimas + patvirtinimas)
8. Mokejimai: deposit (payment_type=deposit) -> DRAFT->PAID. Final (payment_type=final) nekeicia statuso, sukuria patvirtinimo uzklausą (email arba SMS).
9. Patvirtinimo formatas: **Email** (default V2.3) — klientas paspaudzia nuoroda `POST /api/v1/public/confirm-payment/{token}`. **SMS** (legacy) — "TAIP <KODAS>" per Twilio webhook. Abu formatai vienkartiniai, su expires_at.
10. Kanoniniai endpointai (/api/v1): /projects, /projects/{id}, /transition-status, /upload-evidence, /certify-project, /webhook/stripe, /webhook/twilio, /projects/{id}/marketing-consent, /evidences/{id}/approve-for-web, /gallery, **`/projects/{id}/payments/manual`**.
11. Audit log formatas: entity_type, entity_id, action, old_value (JSONB), new_value (JSONB), actor_type, actor_id, ip_address (INET), user_agent, metadata, timestamp.
12. Marketing consent neprivalomas mokejimui; atsaukus sutikima -> show_on_web=false visoms projekto nuotraukoms + audit log.
13. Idempotencija: visi webhook'ai pagal event_id, transition-status idempotentiskas kai new_status == current_status, SMS vienkartinis su bandymu limitu. **Manual mokejimai: idempotencija per `(provider='manual', provider_event_id)` — unikalus globaliai.**

### 0.A Mokejimu Doktrina

Vienintele tiesa apie gautus pinigus yra `payments` faktai:
- `provider='manual'` arba `provider='stripe'`.

`stripe` yra optional kanalas. `manual` (CASH/BANK) yra **default**.

`payments` fakta iveda tas, kas realiai gavo pinigus:
- `SUBCONTRACTOR`, `EXPERT` arba `ADMIN`.

Kiekvienas mokejimo faktas privalo buti:
- idempotentiskas (per `provider_event_id`),
- audituojamas (audit log su PAYMENT_RECORDED_MANUAL arba PAYMENT_RECORDED_STRIPE).

### 0.B DRAFT -> PAID Salyga

`DRAFT -> PAID` leidziama tik jei egzistuoja `DEPOSIT` mokejimo faktas `payments` lenteleje:
- `payment_type='DEPOSIT'`
- `status='SUCCEEDED'`
- `amount > 0`
- `provider IN ('manual','stripe')`

Perejima inicijuoja:
- `SUBCONTRACTOR` arba `ADMIN` per `POST /api/v1/transition-status`.

Backend privalo validuoti, kad mokejimo faktas egzistuoja (`is_deposit_payment_recorded()`).

Isimtis: `payment_type='DEPOSIT_WAIVED'` leidzia perejima be realaus mokejimo (pasitikimi klientai).

### 0.C CERTIFIED -> ACTIVE Salyga (V2.3)

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

---
## 1. SISTEMOS STUBURAS (CORE DOMAIN)

### 1.1 Vienos Tiesos Saltinis
**Principas:** Visa verslo logika, kainodara ir statusu kontrole gyvena **tik FastAPI Backend'e**.

- Visi skaiciavimai atliekami serveryje
- Validacija vykdoma Backend'e
- Statusu perejimai kontroliuojami API lygmenyje
- Frontend'as negali keisti kainos ar statuso

### 1.2 Klientu Architektura
Visi klientai yra **tik duomenu vartotojai**:

| Modulis | Paskirtis | Logikos Lygis |
|---------|-----------|---------------|
| **M1** (Web) | Kliento sasaja | Tik UI/UX |
| **M2** (Eksperto/Rangovo App) | Mobili aplikacija | Tik duomenu rodymas |
| **M3** (AI Logic) | Dirbtinis intelektas | Siulymai, ne sprendimai |

**Kritine taisykle:** Jokios verslo logikos Frontend'e!

### 1.3 Versijavimas
- Visi Core Domain pakeitimai atliekami **tik per backend migracijas**
- Kiekviena migracija turi buti versijuota (Alembic: `20260209_000016_...`)
- Rollback galimybe privaloma
- Audit log visoms struktuuriniams pakeitimams

---

## 2. PROJEKTU STATUSU CIKLAS (FORWARD-ONLY)

### 2.1 Statusu Diagrama

```
DRAFT -> PAID (DEPOSIT) -> SCHEDULED -> PENDING_EXPERT -> CERTIFIED -> ACTIVE
  |         |                |              |              |            |
[Analize] [Depozitas]   [Rangovas]    [Darbai baigti] [Ekspertas] [Email/SMS patvirtinimas]
```

### 2.2 Statusu Aprasymai

#### DRAFT
- **Aprasymas:** Pradine uzklausą
- **Veiksmai:** Analize, samatos kurimas
- **Isejimo salyga:** DEPOSIT mokejimo faktas (manual arba Stripe)
- **Dokumentai:** Preliminari samata

#### PAID (DEPOSIT)
- **Aprasymas:** Sumoketas depozitas (arba WAIVED)
- **Veiksmai:** Generuojama sutartis
- **Isejimo salyga:** SUBCONTRACTOR arba ADMIN per transition-status
- **Dokumentai:** Avanso saskaita faktura, sutartis

#### SCHEDULED
- **Aprasymas:** Rangovas patvirtintas
- **Veiksmai:** Generuojama rangos sutartis
- **Isejimo salyga:** Rangovas priima uzsakyma
- **Dokumentai:** Rangos sutartis, darbo grafikas

#### PENDING_EXPERT
- **Aprasymas:** Rangovas baige darbus
- **Veiksmai:** Reikalingas eksperto vizitas
- **Isejimo salyga:** Min. 3 nuotraukos ikeltos
- **Dokumentai:** Darbu baigimo aktas (preliminarus)

#### CERTIFIED
- **Aprasymas:** Ekspertas patvirtino kokybe
- **Veiksmai:** Laukiama kliento patvirtinimo (email/SMS)
- **Isejimo salyga:** FINAL mokejimas + kliento patvirtinimas (email token arba SMS kodas)
- **Dokumentai:** Sertifikatas (negriztamas)

#### ACTIVE
- **Aprasymas:** Klientas patvirtino per email nuoroda arba SMS zinute
- **Veiksmai:** Aktyvuota abonementine prieziura
- **Isejimo salyga:** N/A (galutinis statusas)
- **Dokumentai:** Galutine saskaita, garantinis lapas

### 2.3 Saugikliai

#### Kliento Patvirtinimo Saugiklis (V2.3)
```python
# CERTIFIED -> ACTIVE pereinama TIK po kliento patvirtinimo
# Email (default): klientas spaudzia nuoroda su tokenu
# SMS (legacy): klientas atsako "TAIP <KODAS>"

# Abu kanalai naudoja client_confirmations lentele:
# - channel: "email" (default) arba "sms"
# - status: "PENDING" -> "CONFIRMED" (arba "EXPIRED")
# - token: unikalus UUID
# - expires_at: galiojimo laikas

# Aktivacija reikalauja ABU:
# 1. payments su payment_type='FINAL', status='SUCCEEDED'
# 2. client_confirmations su status='CONFIRMED'
```

#### Vienkryptcio Perejimo Saugiklis
```python
ALLOWED_TRANSITIONS = {
    "DRAFT": ["PAID"],
    "PAID": ["SCHEDULED"],
    "SCHEDULED": ["PENDING_EXPERT"],
    "PENDING_EXPERT": ["CERTIFIED"],
    "CERTIFIED": ["ACTIVE"],
    "ACTIVE": []  # Galutinis statusas
}

def can_transition(from_status: str, to_status: str) -> bool:
    allowed = ALLOWED_TRANSITIONS.get(from_status, [])
    return to_status in allowed
```

---

## 3. ETAPISKUMAS IR EXIT CRITERIA

### 3.1 I Etapas: Core MVP
**Tikslas:** Pajamos is irengimo

#### Exit Criteria
- >=80% uzsakymu pereina DRAFT -> PAID be klaidu
- Stripe/Manual integracija veikia 99.9% uptime
- Sutarciu generavimas automatizuotas
- Audit log visoms transakcijoms

### 3.2 II Etapas: AI & Robots
**Tikslas:** Mastelis

#### Aktyvavimo Salyga
- 30 dienu stabilumo Lygmenyje 1
- Feature Flags: `ENABLE_VISION_AI = true`
- Zero critical bugs per savaite

#### Funkcionalumas
- AI vizualine analize (sklypo nuotraukos)
- Robotu baziu planavimas
- Automatinis samatu generavimas

### 3.3 III Etapas: Recurring Revenue
**Tikslas:** Pelnas

#### Aktyvavimo Salyga
- Aktyvuojama **tik sertifikuotiems** projektams
- `is_certified = true` DB laukas
- Min. 50 aktyviu abonentu

#### Pajamu Modelis
- Menesinis abonementas: EUR 29.99/men
- Garantinis servisas: 2 vizitai/sezonas
- Papildomos paslaugos: pagal poreiki

---

## 4. AI DIEGIMO IR TEISINE LOGIKA

### 4.1 AI Role Sistemoje

**Pagrindinis Principas:** AI **tik siulo** duomenis, niekada nekeicia projekto statuso.

#### Leistini AI Veiksmai
- Sklypo ploto skaiciavimas is nuotrauku
- Kliuciu aptikimas
- Samatos generavimas (draft)
- Roboto bazes vietos siulymas

#### Draudziami AI Veiksmai
- Statuso keitimas
- Kainos patvirtinimas
- Sutarties pasirasymas
- Sertifikato isdavimas

### 4.2 Audit Trail

Visi AI sugeneruoti laukai turi zyma `generated_by_ai = true`:

```sql
CREATE TABLE project_estimates (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id),
    area_sqm DECIMAL(10,2),
    generated_by_ai BOOLEAN DEFAULT FALSE,
    ai_model_version VARCHAR(50),
    ai_confidence_score DECIMAL(3,2),
    verified_by_expert BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 4.3 Sertifikatas

**Kritine Taisykle:** Sertifikatas yra **negriztamas aktas**.

- Generuojamas **tik** CERTIFIED statuso metu
- Pasirasyomas eksperto
- Turi unikalu numeri
- Saugomas PDF formatu su blockchain hash

---

## 5. TECHNINE UZDUOTIS (API ENDPOINTS)

### 5.1 Statusu Valdymas

#### POST /api/v1/transition-status
**Aprasymas:** Vienintelis legalus kelias keisti statusus

**Request:**
```json
{
    "entity_type": "project",
    "entity_id": "uuid",
    "new_status": "PAID",
    "actor": "ADMIN"
}
```

**Validacija:**
- Forward-only (ALLOWED_TRANSITIONS)
- RBAC (actor_type tikrinamas per `_is_allowed_actor()`)
- Deposit guard (DRAFT->PAID: reikia DEPOSIT payment fact)
- Final + confirmation guard (CERTIFIED->ACTIVE: reikia FINAL payment + client confirmation)
- Idempotentiskas (jei new_status == current_status -> 200 OK)

### 5.2 Projekto Kurimas

#### POST /api/v1/projects
**Aprasymas:** Sukuria pradini DRAFT irasa

### 5.3 Projekto Informacija

#### GET /api/v1/projects/{id}
**Aprasymas:** Grazina pilna busena ir audit log istorija

### 5.4 Irodymu Ikelimas

#### POST /api/v1/upload-evidence
**Aprasymas:** Foto/dokumentu ikelimas (multipart/form-data)

### 5.5 Sertifikavimas

#### POST /api/v1/certify-project
**Aprasymas:** Eksperto veiksmas

**Validacija:**
- Privaloma min. 3 nuotraukos
- Visi checklist punktai pazymeti
- Ekspertas turi galiojancia licencija

### 5.6 Mokejimo Faktu Registravimas

#### POST /api/v1/projects/{id}/payments/manual
**Aprasymas:** Rankinis mokejimo fakto registravimas (CASH/BANK)

**Request:**
```json
{
    "payment_type": "DEPOSIT",
    "amount": 100.00,
    "currency": "EUR",
    "payment_method": "CASH",
    "provider_event_id": "CASH-2026-uniqueid",
    "receipt_no": "CASH-2026-uniqueid",
    "collection_context": "ON_SITE_BEFORE_WORK",
    "notes": "Avansas grynaisiais"
}
```

**Idempotencija:** Pakartotinas kvietimas su tuo paciu `provider_event_id` grazina 200 + `idempotent: true`.

#### POST /api/v1/admin/projects/{id}/payments/deposit-waive
**Aprasymas:** Depozito atleisimas (pasitikimi klientai). ADMIN tik.

### 5.7 Kliento Patvirtinimas (V2.3)

#### POST /api/v1/public/confirm-payment/{token}
**Aprasymas:** Kliento patvirtinimas per email nuoroda (CERTIFIED -> ACTIVE)

**Salyga:** FINAL mokejimas turi buti zafiksuotas, token turi buti galiojantis ir PENDING.

### 5.8 Stripe Webhook

#### POST /api/v1/webhook/stripe
**Aprasymas:** Stripe mokejimo webhook'as

### 5.9 Twilio SMS Webhook

#### POST /api/v1/webhook/twilio
**Aprasymas:** Twilio SMS webhook'as (legacy aktyvacija)

---

## 6. EKSPERTO SERTIFIKAVIMO CHECKLIST'AS

### 6.1 Privalomi Foto Reikalavimai

**Minimumas:** 3-5 kontrolines nuotraukos

| # | Nuotrauka | Aprasymas | Privaloma |
|---|-----------|-----------|-----------|
| 1 | Bendras vaizdas | Visas sklypas is virsaus/sono | Taip |
| 2 | Pagrindo lygumas | Artimesnis vaizdas zoles pavirsiaus | Taip |
| 3 | Krastu apdirbimas | Perimetro zona | Taip |
| 4 | Roboto baze | Irengta ir stabili | Rekomenduojama |
| 5 | Perimetro kabelis | Vientisumas, tvirtinimas | Rekomenduojama |

**Blokavimas:** Be min. 3 nuotrauku sertifikavimas **neimanomas**.

### 6.2 Vertinimo Kriterijai

#### Pagrindo Lygumas
- Nera duobiu > 2 cm gylio
- Nera kauburiu > 3 cm aukscio
- Nuolydis <= 25 laipsniu (robotui saugus)

#### Sejos Tolygumas
- Zoles tankumas >= 80% ploto
- Nera pliku demiu > 0.5 m2
- Vienoda augimo faze

#### Krastu Apdirbimas
- Aiskiai apibrezta riba
- Perimetro kabelis 5-10 cm nuo krasto
- Nera pazeisitu vietu

#### Roboto Bazes Stabilumas
- Lygi platforma
- Elektros prijungimas saugus
- Apsauga nuo lietaus

#### Perimetro Kabelio Vientisumas
- Nera pertrukiu
- Tvirtinimas kas 75 cm
- Signalo stiprumas > 80%

#### Sklypo Svara
- Pasalintos statybines atliekos
- Nera pavojingu objektu
- Estetiskas vaizdas

### 6.3 Sertifikavimo Procesas

```
Rangovas baigia darbus
  -> Ikelia min. 3 nuotraukas
  -> Statusas: PENDING_EXPERT
  -> Ekspertas gauna pranesima
  -> Ekspertas atvyksta i vieta
  -> Uzpildo checklist
  -> Visi kriterijai OK?
    -> Taip: Isduoda sertifikata -> CERTIFIED
    -> Ne: Grazina rangovui taisyti -> PENDING_EXPERT
```

---

## 7. NEUZRASYTOS, BET PRIVALOMOS TAISYKLES

### 7.1 Marzu Neliestciamumas

**Principas:** Marzos keiciamos **tik per admin panele** su Audit Log.

#### Draudziama
- Tiesioginis DB pakeitimas (`UPDATE margins SET ...`)
- Marzu keitimas per API be autentifikacijos
- Frontend'e hardcoded marzos

#### Leidziama
- Admin panele su autentifikacija
- Audit log kiekvienam pakeitimui
- Versijuotos marzu lenteles

### 7.2 Feature Flags

**Principas:** Lygio 2 ir 3 moduliai isjungti pagal nutylëjimą.

Visos feature flags apibreztos `backend/app/core/config.py::Settings` klaseje.
Pilnas sarąsas su reiksm'emis: `backend/.env.example`.

```python
# Naudojimas (endpoint lygyje):
settings = get_settings()
if not settings.enable_finance_ledger:
    raise HTTPException(404, "Not Found")
```

### 7.3 No Undo Policy

**Principas:** Klaidos taisomos kuriant nauja projekta arba papildoma sertifikata, **ne "atstatant" statusa**.

**Scenarijus 1:** Klaidingai sumoketaas depozitas
```python
# BLOGAI
project.status = "DRAFT"  # Negalima grizti atgal

# GERAI
refund = create_refund(project_id, amount)
new_project = create_project(client_id, corrected_data)
```

**Scenarijus 2:** Sertifikatas isduotas per klaida
```python
# BLOGAI
certificate.revoke()  # Sertifikatai negriztami

# GERAI
corrective_certificate = create_corrective_certificate(
    original_cert_id=cert.id,
    reason="Klaidingai ivertinta sejos kokybe",
    corrective_actions=["Papildomas sejimas", "Pakartotinis vizitas"]
)
```

### 7.4 Admin UI PII Politika (griezta)

**Principas:** Admin UI neturi rodyti pilno PII (email/phone) pagal nutylejima.

- Visi "Klientu modulio" endpointai turi grazinti tik **maskuotus** kontaktus.
- Nera MVP scope "Reveal" funkcijos (jei reikes ateityje: superadmin-only + reason + audit trail).

### 7.5 Admin UI tik workflow veiksmai

**Principas:** Nera "Set status" mygtuko admin UI. Statusas keiciamas tik per:
- `POST /api/v1/transition-status` (kanoninis kelias) arba
- admin-only override, kai tai oficialiai leidziama (pvz. `admin-confirm` su privalomu `reason` ir audit logu).

---

## 8. PRINCIPAI, KURIU NIEKADA NEKEICIAME

### 8.1 AI yra Pagalbininkas, Ne Sprendejas

AI GALI:
- Siulyti ploto skaiciavima
- Aptikti kliutis
- Generuoti draft samata
- Rekomenduoti roboto bazes vieta

AI NEGALI:
- Keisti projekto statuso
- Patvirtinti kainos
- Pasirasyti sutarties
- Isduoti sertifikato

### 8.2 Ekspertas Turi Veto Teise

**Principas:** Tik agronomas aktyvuoja garantini servisa.

- Ekspertas gali atmesti darba, net jei AI analize teigiama
- Ekspertas gali reikalauti papildomu nuotrauku
- Ekspertas gali sustabdyti projekta bet kuriame etape
- Eksperto sprendimas yra galutinis

### 8.3 Klientas Negaista Laiko

**Tikslas:** Visi zingsniai <= 2 mygtuku patirtis.

| Etapas | Veiksmai | Mygtukai |
|--------|----------|----------|
| 1. Uzklausą | Ivesti adresa, ikelti nuotrauka | 2 |
| 2. Samata | Perziureti, patvirtinti | 1 |
| 3. Mokejimas | Stripe / grynieji | 1 |
| 4. Patvirtinimas | Email nuoroda arba SMS "TAIP" | 1 |

### 8.4 Vienos Tiesos Saltinis

**Principas:** Viskas uzrakinta Backend'e.

```
FRONTEND (M1, M2, M3) — tik skaito, rodo UI, siuntcia uzklausas
        |
        v
FASTAPI BACKEND — verslo logika, validacija, kainodara, statusu kontrole, audit log
        |
        v
POSTGRESQL DATABASE — single source of truth, ACID garantijos, audit trail
```

### 8.5 Audit Log Privalomas

**Principas:** Visoms kainoms ir statusams.

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL,
    old_value JSONB,
    new_value JSONB,
    actor_type VARCHAR(50) NOT NULL,
    actor_id UUID,
    timestamp TIMESTAMP DEFAULT NOW(),
    ip_address INET,
    user_agent TEXT,
    metadata JSONB
);
```

---

## PRIEDAI

### A. Statusu Perejimu Matrica

| Is \ I | DRAFT | PAID | SCHEDULED | PENDING_EXPERT | CERTIFIED | ACTIVE |
|--------|-------|------|-----------|----------------|-----------|--------|
| DRAFT | - | Taip | Ne | Ne | Ne | Ne |
| PAID | Ne | - | Taip | Ne | Ne | Ne |
| SCHEDULED | Ne | Ne | - | Taip | Ne | Ne |
| PENDING_EXPERT | Ne | Ne | Ne | - | Taip | Ne |
| CERTIFIED | Ne | Ne | Ne | Ne | - | Taip |
| ACTIVE | Ne | Ne | Ne | Ne | Ne | - |

### B. Roliu ir Teisiu Matrica

| Veiksmas | Klientas | Rangovas | Ekspertas | Admin |
|----------|----------|----------|-----------|-------|
| Sukurti projekta | Taip | Ne | Ne | Taip |
| Perziureti samata | Taip | Taip | Taip | Taip |
| Moketi depozita | Taip | Taip | Ne | Taip |
| Priimti uzsakyma | Ne | Taip | Ne | Taip |
| Ikelti nuotraukas | Ne | Taip | Taip | Taip |
| Sertifikuoti | Ne | Ne | Taip | Taip |
| Keisti marzas | Ne | Ne | Ne | Taip |

### C. Dokumentu Generavimo Taisykles

| Dokumentas | Statusas | Generuojamas | Pasirasyomas |
|------------|----------|--------------|-------------|
| Preliminari samata | DRAFT | Automatiskai | Ne |
| Avanso saskaita | PAID | Automatiskai | Ne |
| Sutartis | PAID | Automatiskai | Klientas (e-parasas) |
| Rangos sutartis | SCHEDULED | Automatiskai | Rangovas |
| Sertifikatas | CERTIFIED | Automatiskai | Ekspertas |
| Galutine saskaita | ACTIVE | Automatiskai | Ne |

### D. Kontaktai ir Atsakomybes

| Role | Atsakomybe | Kontaktas |
|------|------------|-----------|
| **Tech Lead** | Backend architektura | tech@vejapro.lt |
| **Product Owner** | Verslo logika | product@vejapro.lt |
| **Agronomas** | Sertifikavimo standartai | expert@vejapro.lt |
| **DevOps** | Infrastruktura | devops@vejapro.lt |

---

## VERSIJU ISTORIJA

| Versija | Data | Pakeitimai |
|---------|------|------------|
| **V.2** | 2026-02-09 | Konsoliduota V1.3 + V1.4: payments-first doktrina, manual default, SYSTEM_EMAIL, email aktyvacija |
| V.1.4 | 2026-02-09 | Payments-first korekcija, manual default, Stripe optional, V2.3 email aktyvacija |
| V.1.3 | 2026-02-02 | Pilna dokumentacija, API endpoints, audit log |
| V.1.2 | 2026-01-15 | Feature flags, SMS patvirtinimas |
| V.1.1 | 2025-12-01 | AI integracijos taisykles |
| V.1.0 | 2025-11-01 | Pradine konstitucija |

---

(c) 2026 VejaPRO. Visos teises saugomos.

Si konstitucija yra **vidine technine specifikacija** ir negali buti platinama be rastisko leidimo.

**Paskutinis atnaujinimas:** 2026-02-09
**Dokumenta tvirtino:** Tech Lead & Product Owner
**Kita perziura:** 2026-03-01
