# VejaPRO V2.3 Finansu Modulio Rekonstrukcija — Pakeitimu Poveikio Analize

**Data:** 2026-02-09
**Statusas:** ANALIZ BAIGTA
**Scope:** Pilnas failinis pakeitimu zemelis (gap analysis vs. esama V1.52/V2.2 architektura)

---

## TURINYS

1. [Santrauka](#1-santrauka)
2. [Moduliu poveikio matrica](#2-moduliu-poveikio-matrica)
3. [Detali failu analize](#3-detali-failu-analize)
4. [Nauji failai (reikia sukurti)](#4-nauji-failai)
5. [Migraciju planas](#5-migraciju-planas)
6. [Konfiguraciju pakeitimai](#6-konfiguraciju-pakeitimai)
7. [Testu pokytis](#7-testu-pokytis)
8. [Dokumentu atnaujinimai](#8-dokumentu-atnaujinimai)
9. [Deploy checklist](#9-deploy-checklist)

---

## 1. SANTRAUKA

### Esama busena (V1.52 / V2.2):
- `payments` lentele jau turi: `payment_method`, `provider_event_id`, `is_manual_confirmed`, `proof_url`, `received_at`, `collected_by`, `confirmed_by` (prideta migracijoje `000008`)
- `transition_service.py` jau turi: `is_deposit_payment_recorded()` su WAIVED logika, `is_final_payment_recorded()`, `apply_transition()` su RBAC
- `client_confirmations` lentele egzistuoja (migracija `000015`), bet default channel="sms"
- Finance ledger modulis (`finance.py`) jau turi: quick-payment, document upload, SHA-256 dedupe, vendor rules
- Notification outbox veikia su: sms, email, whatsapp_ping kanalais
- AI finance extract: tik placeholder (stub)
- Admin IP allowlist: grazina **403** (ne 404)
- PII redaction: veikia audit_logs laukuose, bet **ne** `ai_extracted_data`
- SSE metrics endpoint: **neegzistuoja**
- `CERTIFIED -> ACTIVE` validacija: tikrina tik FINAL payment, **netikrina** `client_confirmations(CONFIRMED)`

### V2.3 reikalauja (pagrindiniai gap'ai):

| # | Gap | Sunkumas |
|---|-----|----------|
| G1 | `payments.ai_extracted_data` JSONB laukas neegzistuoja | Migracija |
| G2 | `UNIQUE(provider, provider_event_id)` indeksas neegzistuoja | Migracija |
| G3 | CERTIFIED->ACTIVE netikrina client_confirmations(CONFIRMED) | Kodo pakeitimas |
| G4 | Admin IP allowlist grazina 403 vietoj 404 | Kodo pakeitimas |
| G5 | Feature flag off grazina 404, bet admin check grazina 403 | Kodo pakeitimas |
| G6 | client_confirmations default channel="sms", reikia "email" | Migracija + kodas |
| G7 | SSE metrics endpoint neegzistuoja | Naujas kodas |
| G8 | AI ingest i payments.ai_extracted_data neimplementuotas | Naujas kodas |
| G9 | PII redaction netaikomas ai_extracted_data | Kodo pakeitimas |
| G10 | quick-payment FINAL nekeicia kanalo i email (naudoja sms) | Kodo pakeitimas |
| G11 | quick-payment neturi `SELECT ... FOR UPDATE` ant projekto | Kodo pakeitimas |
| G12 | Audit action "finance_payment_recorded" (V2.3 nomenklatura) vs dabartinis "PAYMENT_RECORDED_MANUAL" | Nomenklaturos suderinimas |
| G13 | DEPOSIT idempotency 409 konflikto atsakymas neimplementuotas | Kodo pakeitimas |
| G14 | provider_event_id deterministine generavimo schema nevaliduojama | Kodo pakeitimas |
| G15 | ENABLE_FINANCE_METRICS config neegzistuoja | Config + kodas |
| G16 | SSE rate-limit ir max concurrent connections neimplementuoti | Naujas kodas |
| G17 | SMS kanalas vis dar aktyvus FINAL payment confirmation flow | Kodo pakeitimas |

---

## 2. MODULIU POVEIKIO MATRICA

| Modulis / Failas | Pokycio tipas | Prioritetas | Sudekingumas |
|-------------------|---------------|-------------|--------------|
| **DB Migracija (nauja)** | CREATE | P0 | Vidutinis |
| **app/models/project.py** | ALTER (Payment, ClientConfirmation) | P0 | Mazas |
| **app/services/transition_service.py** | MODIFY (CERTIFIED->ACTIVE validacija) | P0 | Vidutinis |
| **app/api/v1/finance.py** | MODIFY (quick-payment, row-lock, channels) | P0 | Didelis |
| **app/api/v1/projects.py** | MODIFY (FINAL flow: SMS->Email, idempotency 409) | P0 | Didelis |
| **app/core/config.py** | ADD (ENABLE_FINANCE_METRICS, SSE settings) | P0 | Mazas |
| **app/main.py** | MODIFY (404 strategija vietoj 403) | P0 | Mazas |
| **app/schemas/finance.py** | MODIFY (QuickPaymentResponse: sms_queued -> email_queued) | P1 | Mazas |
| **app/schemas/project.py** | Minimalus (gali reiketi papildymu) | P2 | Mazas |
| **app/services/notification_outbox.py** | Minimalus (jau palaiko email) | P2 | Mazas |
| **app/services/notification_outbox_channels.py** | Minimalus (jau veikia) | P2 | Mazas |
| **app/services/ai/finance_extract/service.py** | CREATE (implementuoti AI ekstrakcija) | P1 | Didelis |
| **app/services/ai/finance_extract/contracts.py** | MODIFY (papildyti kontraktus) | P1 | Mazas |
| **app/api/v1/finance.py** (metrics) | ADD (SSE metrics endpoint) | P1 | Vidutinis |
| **app/static/finance.html** | MODIFY (UI: One-Click Confirm, AI auto-fill) | P1 | Vidutinis |
| **Testu failai** | MODIFY/ADD (nauji test case'ai) | P0 | Vidutinis |
| **Dokumentacija** | MODIFY (4 dokumentai) | P1 | Mazas |

---

## 3. DETALI FAILU ANALIZE

### 3.1 `backend/app/migrations/versions/` — NAUJA MIGRACIJA

**Failas:** `20260209_000016_v23_finance_reconstruction.py` (SUKURTI)

**Veiksmai:**
```
1. ALTER TABLE payments ADD COLUMN ai_extracted_data JSONB NULL
2. CREATE UNIQUE INDEX uniq_provider_event ON payments(provider, provider_event_id)
   - PASTABA: esamas kodas jau naudoja (provider, provider_event_id) idempotency check,
     bet DB lygiu UNIQUE constraint neegzistuoja. Reikia patikrinti ar nera duplikatu pries
     kuriant indeksa (IF NOT EXISTS arba data cleanup).
3. ALTER TABLE client_confirmations ALTER COLUMN channel SET DEFAULT 'email'
   - Dabartinis default: 'sms' (project.py:161, migracija 000015)
```

**Riskos:**
- Jei DB jau turi payment irasu su dubliuojanciu (provider, provider_event_id), UNIQUE indeksas nepraseis. Reikia priesinesnio cleanup skripto.
- `ai_extracted_data` yra nullable, todeel ALTER TABLE yra safe (no rewrite).

---

### 3.2 `backend/app/models/project.py`

**Eilutes:** 127-149 (Payment klase)

**Pakeitimai:**

| Eilute | Dabartine busena | V2.3 reikalavimas | Veiksmas |
|--------|------------------|-------------------|----------|
| ~140 | `payment_method = Column(String(32))` | Turi buti NOT NULL su ENUM check | ADD CHECK constraint migracijoje |
| ~134 | `provider_event_id = Column(String(128))` | `TEXT NOT NULL` + UNIQUE(provider, provider_event_id) | ADD NOT NULL migracijoje + UNIQUE indeksas |
| Naujas | Neegzistuoja | `ai_extracted_data = Column(JSON_TYPE)` | ADD stulpeli |
| 161 | `channel = Column(... default="sms", server_default=text("'sms'"))` | default turi buti "email" | CHANGE default |

**Konkretus kodo pakeitimai:**

```python
# Payment klase - prideti po proof_url (eilute ~145):
ai_extracted_data = Column(JSON_TYPE)  # V2.3: AI extraction results

# ClientConfirmation klase - pakeisti default (eilute 161):
# IS:  channel = Column(String(20), nullable=False, default="sms", server_default=text("'sms'"))
# TO:  channel = Column(String(20), nullable=False, default="email", server_default=text("'email'"))
```

---

### 3.3 `backend/app/services/transition_service.py`

**Failas:** 277 eilutes

**GAP G3: CERTIFIED -> ACTIVE validacija**

**Dabartine busena (eilute 155-157):**
```python
if new_status == ProjectStatus.ACTIVE:
    if not is_final_payment_recorded(db, str(project.id)):
        raise HTTPException(400, "Final payment not recorded")
```

**V2.3 reikalauja:**
```
CERTIFIED -> ACTIVE:
  Pre-conditions:
    1. egzistuoja client_confirmations su status=CONFIRMED
    2. IR egzistuoja payments su payment_type=FINAL, status=SUCCEEDED
```

**Reikalingas pakeitimas:**
```python
# Prideti nauja funkcija:
def is_client_confirmed(db: Session, project_id: str) -> bool:
    confirmation = (
        db.query(ClientConfirmation)
        .filter(
            ClientConfirmation.project_id == project_id,
            ClientConfirmation.status == "CONFIRMED",
        )
        .first()
    )
    return confirmation is not None

# Pakeisti apply_transition() (eilute 155-157):
if new_status == ProjectStatus.ACTIVE:
    if not is_final_payment_recorded(db, str(project.id)):
        raise HTTPException(400, "Final payment not recorded")
    if not is_client_confirmed(db, str(project.id)):
        raise HTTPException(400, "Client confirmation not received")
```

**Papildomai:** PII redaction turi apimti ir `ai_extracted_data` lauka, jei jis ateina per metadata. Dabartine `_redact_pii()` funkcija (eilutes 40-53) jau veikia rekursyviai ant dict/list, todeel jei `ai_extracted_data` bus perduotas per `new_value` ar `metadata` — PII bus redaguojamas. Taciau reikia **patikrinti**, kad visi audit call'ai, kurie logina AI data, perduoda ja per redaguojamus laukus.

---

### 3.4 `backend/app/api/v1/finance.py`

**Failas:** 965 eilutes — didžiausias pokytis

#### 3.4.1 Quick-Payment DEPOSIT (eilutes 371-504)

**GAP G11: Truksta `SELECT ... FOR UPDATE` ant projekto**

**Dabartine busena (eilute 381):**
```python
project = db.get(Project, project_id)
```

**V2.3 reikalauja:**
```python
project = db.execute(
    select(Project).where(Project.id == project_id).with_for_update()
).scalar_one_or_none()
```

#### 3.4.2 Quick-Payment FINAL — kanalas (eilutes 478-493)

**GAP G10/G17: Naudojamas SMS vietoj Email**

**Dabartine busena (eilute 479):**
```python
token = create_client_confirmation(db, str(project.id))  # default channel="sms"
```

**V2.3 reikalauja:**
```python
# 1. Patikrinti ar email prieinamas
settings = get_settings()
if not settings.enable_email_intake:
    raise HTTPException(400, "FIN_CHANNEL_UNAVAILABLE")

client_email = None
if isinstance(project.client_info, dict):
    client_email = project.client_info.get("email")
if not client_email:
    raise HTTPException(400, "FIN_CHANNEL_UNAVAILABLE")

# 2. Sukurti confirmation su channel="email"
token = create_client_confirmation(db, str(project.id), channel="email")

# 3. Enqueue email per notification_outbox
from app.services.notification_outbox import enqueue_notification
enqueue_notification(
    db,
    entity_type="project",
    entity_id=str(project.id),
    channel="email",
    template_key="FINAL_PAYMENT_CONFIRMATION",
    payload_json={
        "to": client_email,
        "subject": "VejaPRO - Patvirtinkite galutini mokejima",
        "body_text": f"Jusu patvirtinimo kodas: {token}",
    },
)

# 4. Optionally: WhatsApp ping
if settings.enable_whatsapp_ping:
    whatsapp_consent = (project.client_info or {}).get("whatsapp_consent", False)
    phone = (project.client_info or {}).get("phone")
    if whatsapp_consent and phone:
        enqueue_notification(
            db,
            entity_type="project",
            entity_id=str(project.id),
            channel="whatsapp_ping",
            template_key="FINAL_PAYMENT_WHATSAPP_PING",
            payload_json={"to": phone, "message": "Gavome mokejima. Patikrinkite el. pasta."},
        )
```

#### 3.4.3 Audit action nomenklatura

**Dabartine busena (eilute 443):**
```python
action="PAYMENT_RECORDED_MANUAL"
```

**V2.3 nomenklatura:**
```python
action="finance_payment_recorded"  # arba palikti esama ir dokumentuoti atitikima
```

**Rekomendacija:** Palikti esama `PAYMENT_RECORDED_MANUAL` (nekeisti istoriniu auditu), bet prideti V2.3 alias i dokumentacija.

#### 3.4.4 DEPOSIT idempotency su 409 (GAP G13)

**Dabartine busena (eilutes 397-411):** Grazina 200 "already recorded" visais atvejais.

**V2.3 reikalauja:**
```
- jei identiska semantika -> 200 "already recorded"
- jei konfliktuoja -> 409
```

**Reikalingas pakeitimas:**
```python
existing = (
    db.query(Payment)
    .filter(Payment.provider == "manual", Payment.provider_event_id == payload.provider_event_id)
    .first()
)
if existing:
    # Tikrinti ar semantika sutampa
    if (existing.payment_type == payment_type
        and existing.project_id == project.id
        and float(existing.amount) == float(amount)):
        return QuickPaymentResponse(
            success=True,
            payment_id=str(existing.id),
            payment_type=existing.payment_type,
            amount=float(existing.amount),
            status_changed=False,
            new_status=project.status,
        )
    else:
        raise HTTPException(409, "Conflict: provider_event_id jau panaudotas su kitais parametrais")
```

#### 3.4.5 Naujas SSE Metrics Endpoint (GAP G7)

**Neegzistuoja. Reikia sukurti:**

```
GET /admin/finance/metrics (SSE)
- Gated by: ENABLE_FINANCE_METRICS=true
- 404 strategija (flag off / IP / ne admin)
- Be PII
- Metrikos: avg_attempts, reject_rate, manual_vs_stripe_ratio, avg_confirm_time, daily_volume
- Rate-limit + max concurrent SSE
```

**Siuloma vieta:** `backend/app/api/v1/finance.py` (prideti nauja endpoint) ARBA sukurti atskira `finance_metrics.py`.

---

### 3.5 `backend/app/api/v1/projects.py`

**Failas:** 2408 eilutes

#### 3.5.1 Manual Payment FINAL flow (eilutes 1144-1209)

**GAP G17: SMS->Email perkelimas**

**Dabartine busena:** Kuria `client_confirmation` su default channel="sms", siunciant per Twilio `send_sms()`.

**V2.3 reikalauja:** Analogiskas pakeitimas kaip finance.py — naudoti email kanal per notification_outbox.

**Konkretus pokytis (eilutes 1144-1209):**
```python
# VIETOJ:
if payment_type == PaymentType.FINAL.value and project.status == ProjectStatus.CERTIFIED.value:
    token = create_client_confirmation(db, str(project.id))
    # ... SMS siuntimas per Twilio ...

# V2.3:
if payment_type == PaymentType.FINAL.value and project.status == ProjectStatus.CERTIFIED.value:
    settings = get_settings()
    client_email = (project.client_info or {}).get("email") if isinstance(project.client_info, dict) else None

    if not settings.enable_email_intake or not client_email:
        # Rollback negalimas cia (payment jau sukurtas), bet loginame warning
        create_audit_log(db, ..., action="FIN_CHANNEL_UNAVAILABLE", ...)
    else:
        token = create_client_confirmation(db, str(project.id), channel="email")
        enqueue_notification(db, channel="email", template_key="FINAL_PAYMENT_CONFIRMATION", ...)
        create_audit_log(db, ..., action="EMAIL_CONFIRMATION_CREATED", ...)
```

#### 3.5.2 Stripe Webhook FINAL flow (eilutes 2145-2211)

**Tas pats SMS->Email pokytis.** Dabartine logika siunciant SMS per Twilio turi buti pakeista i email per notification_outbox.

**Papildomai:** Stripe webhook turi fiksuoti `actor_type=SYSTEM_STRIPE` (jau daroma, eilute 2139).

#### 3.5.3 Twilio Webhook — CERTIFIED->ACTIVE (eilutes 2218-2407)

**V2.3 doktrina:** `CERTIFIED -> ACTIVE` leidziamas tik po `client_confirmations(CONFIRMED)` IR `FINAL payment(SUCCEEDED)`.

**Dabartine busena:** Twilio webhook (SMS atsakymas) tvirtina confirmation ir kvieciant `apply_transition` perkelia i ACTIVE. Tai teisingas flow — tik `apply_transition` turi tikrinti abu pre-conditions (jau sprendeme G3).

**Papildomas pokytis:** Kadangi V2.3 sako "SMS isjungtas" — Twilio webhook FINAL confirmation flow turi buti **pakeistas email confirmation flow**. Taciau:
- Twilio webhook lieka SMS gavimui (kitoms reikmems)
- Nauju email confirmation endpoint reikia (pvz. `POST /public/confirm-payment/{token}`)

**NAUJAS ENDPOINT:**
```
POST /api/v1/public/confirm-payment/{token}
- Viesas (be auth)
- Validuoja token (hash lookup)
- Tikrina: confirmation.status == PENDING, not expired
- Tikrina: project.status == CERTIFIED
- Tikrina: FINAL payment egzistuoja
- Zymi confirmation kaip CONFIRMED
- Kvieciant apply_transition(CERTIFIED -> ACTIVE, actor_type="SYSTEM_EMAIL")
```

---

### 3.6 `backend/app/core/config.py`

**Failas:** 409 eilutes

**Nauji settings (prideti):**

```python
# V2.3 Finance Metrics
enable_finance_metrics: bool = Field(
    default=False,
    validation_alias=AliasChoices("ENABLE_FINANCE_METRICS"),
)
finance_metrics_max_sse_connections: int = Field(
    default=10,
    validation_alias=AliasChoices("FINANCE_METRICS_MAX_SSE_CONNECTIONS"),
)
finance_metrics_rate_limit_per_min: int = Field(
    default=30,
    validation_alias=AliasChoices("FINANCE_METRICS_RATE_LIMIT_PER_MIN"),
)
```

**Esami settings — be pakeitimu:**
- `enable_finance_ledger` — jau egzistuoja
- `enable_finance_ai_ingest` — jau egzistuoja
- `pii_redaction_enabled` — jau egzistuoja
- `enable_email_intake` — jau egzistuoja
- `enable_whatsapp_ping` — jau egzistuoja
- `admin_ip_allowlist_raw` — jau egzistuoja

---

### 3.7 `backend/app/main.py`

**Failas:** 353 eilutes

#### 3.7.1 GAP G4: 404 Security Strategy

**Dabartine busena (eilutes 244-254):**
```python
@app.middleware("http")
async def admin_ip_allowlist_middleware(request: Request, call_next):
    ...
    if not _ip_in_allowlist(ip, allowlist):
        return JSONResponse(status_code=403, content={"detail": "Admin IP not allowed"})
```

**V2.3 reikalauja:**
```python
# Keisti 403 -> 404 ir pakeisti detail teksta
if not _ip_in_allowlist(ip, allowlist):
    return JSONResponse(status_code=404, content={"detail": "Nerastas"})
```

**Papildomai:** 404 strategija turi galioti ir non-admin endpointams po `/admin/finance/*` kai:
- Feature flag isjungtas
- IP ne allowlist
- Nera admin role

**Dabartinis `_require_finance_enabled()` (finance.py:54-57):**
```python
def _require_finance_enabled():
    settings = get_settings()
    if not settings.enable_finance_ledger:
        raise HTTPException(404, "Nerastas")  # <-- Jau grazina 404!
```
Sis jau atitinka V2.3. Tik admin IP middleware reikia pataisyti (403->404).

---

### 3.8 `backend/app/services/ai/finance_extract/service.py`

**Dabartine busena:** Tuscias placeholder (8 eilutes).

**V2.3 reikalauja:** AI ekstrakcija is PDF/nuotraukos -> `payments.ai_extracted_data` su `confidence` ir `model_version`.

**Reikalingas implementavimas:**
```python
# Nauja logika:
async def extract_finance_document(
    file_bytes: bytes,
    filename: str,
    provider: str = "claude",  # arba kitas AI provider
) -> dict:
    """
    AI istraukia suma, data, tiekeja is PDF/nuotraukos.
    Grazina: {amount, date, vendor, confidence, model_version, raw_extraction}
    """
    # Naudoti AI provider per router.resolve("finance_extract", ...)
    # Rezultata irasyti i payments.ai_extracted_data
    # Jei confidence > 0.95: UI leidzia auto-fill
    # DRAUDZIAMA: automatinis confirm be admin veiksmo
```

**Priklausomybes:**
- `app/services/ai/common/router.py` — prideti "finance_extract" scope
- `app/services/ai/finance_extract/contracts.py` — papildyti su `model_version`
- `app/api/v1/finance.py` — integruoti ekstrakcija i document extract endpoint

---

### 3.9 `backend/app/services/ai/finance_extract/contracts.py`

**Dabartine busena (17 eiluciu):**
```python
class AIFinanceExtractResult(BaseModel):
    vendor_name: str = ""
    amount: float = 0.0
    currency: str = "EUR"
    date: str = ""
    description: str = ""
    confidence: float = 0.0
```

**V2.3 reikalauja prideti:**
```python
    model_version: str = ""
    raw_extraction: dict = {}  # AI raw output (for audit)
```

---

### 3.10 `backend/app/services/notification_outbox.py`

**Failas:** 197 eilutes — **minimalus pokytis**

Dabartine busena jau palaiko: `sms`, `email`, `whatsapp_ping` kanalus.
Pokyciai: nera. Logika jau tinkama V2.3.

**Vienintelis dalykas:** Uzfiksuoti kad SMS kanalas NEBENAUDOJAMAS FINAL payment confirmation flow. Taciau outbox infrastuktura jo nepasalina (ateiciui).

---

### 3.11 `backend/app/services/notification_outbox_channels.py`

**Failas:** 190 eiluciu — **minimalus pokytis**

- Email siuntimas jau veikia (SMTP)
- WhatsApp ping stub jau egzistuoja
- SMS "legacy path" jau atskirtas

**Pokyciai:** Nera. Dabartine implementacija atitinka V2.3.

---

### 3.12 `backend/app/schemas/finance.py`

**Failas:** 204 eilutes

**Pakeitimai:**

```python
# QuickPaymentResponse (eilute 196-203):
# Pakeisti:
#   sms_queued: bool = False
# I:
#   email_queued: bool = False
#   whatsapp_pinged: bool = False

# Prideti payment_method i ENUM check:
class PaymentMethodEnum(StrEnum):
    CASH = "CASH"
    BANK_TRANSFER = "BANK_TRANSFER"
    WAIVED = "WAIVED"  # V2.3: prideti WAIVED
```

**PASTABA:** Dabartine `FinancePaymentMethod` turi `CARD` ir `OTHER` — V2.3 specifikacija mini tik `CASH`, `BANK_TRANSFER`, `WAIVED`. Reikia nusprest ar palikti atgalini suderinamuma.

---

### 3.13 `backend/app/schemas/project.py`

**Failas:** 290 eiluciu — **mazas pokytis**

- `ManualPaymentRequest` jau turi `provider_event_id` (eilute 245)
- `TransitionRequest` jau veikia teisingai

**Potencialus pokytis:** Prideti `ai_extracted_data` i `ManualPaymentResponse` arba atskira schema.

---

## 4. NAUJI FAILAI (REIKIA SUKURTI)

### 4.1 Migracija: `20260209_000016_v23_finance_reconstruction.py`

```
Veiksmai:
1. ALTER TABLE payments ADD COLUMN ai_extracted_data JSONB NULL
2. CREATE UNIQUE INDEX uniq_payments_provider_event
   ON payments(provider, provider_event_id)
   WHERE provider_event_id IS NOT NULL
3. ALTER TABLE client_confirmations ALTER COLUMN channel SET DEFAULT 'email'
4. ALTER TABLE payments ADD CONSTRAINT chk_payment_method_enum
   CHECK (payment_method IN ('CASH','BANK_TRANSFER','CARD','WAIVED','OTHER'))
   -- arba be CARD/OTHER jei V2.3 griežtai apriboja
```

### 4.2 Email confirmation endpoint (viesa)

**Siulomas failas:** Prideti i `backend/app/api/v1/projects.py` arba `backend/app/api/v1/intake.py`

```
POST /api/v1/public/confirm-payment/{token}
- Viesas (be JWT auth)
- Rate limited
- Validuoja token hash
- Tikrina expiration
- Tikrina project status == CERTIFIED
- Tikrina FINAL payment exists
- Marks confirmation as CONFIRMED
- Calls apply_transition(CERTIFIED -> ACTIVE, actor_type="SYSTEM_EMAIL")
- Audit: "EMAIL_CONFIRMATION_CONFIRMED"
```

### 4.3 SSE Metrics endpoint

**Siulomas failas:** Prideti i `backend/app/api/v1/finance.py`

```
GET /api/v1/admin/finance/metrics
- SSE (Server-Sent Events)
- Gated: ENABLE_FINANCE_METRICS
- 404 strategija
- Tik agregatai, be PII:
  - avg_attempts (confirmation bandymu vidurkis)
  - reject_rate (atmestimu dalis)
  - manual_vs_stripe_ratio
  - avg_confirm_time (nuo payment iki confirmation)
  - daily_volume (dienos mokejumu suma)
- Rate-limit: finance_metrics_rate_limit_per_min
- Max concurrent: finance_metrics_max_sse_connections
```

---

## 5. MIGRACIJU PLANAS

### Migraciju seka:

```
000016_v23_finance_reconstruction.py:
  upgrade():
    1. op.add_column('payments', sa.Column('ai_extracted_data', JSONB, nullable=True))
    2. op.create_unique_constraint(
         'uniq_payments_provider_event',
         'payments',
         ['provider', 'provider_event_id']
       )
    3. op.alter_column('client_confirmations', 'channel',
         server_default=sa.text("'email'"))
    4. op.execute("""
         ALTER TABLE payments ADD CONSTRAINT chk_payment_method_values
         CHECK (payment_method IS NULL OR payment_method IN
                ('CASH','BANK_TRANSFER','CARD','WAIVED','OTHER'))
         NOT VALID
       """)
       op.execute("ALTER TABLE payments VALIDATE CONSTRAINT chk_payment_method_values")

  downgrade():
    1. op.drop_constraint('chk_payment_method_values', 'payments')
    2. op.alter_column('client_confirmations', 'channel',
         server_default=sa.text("'sms'"))
    3. op.drop_constraint('uniq_payments_provider_event', 'payments')
    4. op.drop_column('payments', 'ai_extracted_data')
```

**SVARBU:** Pries deploy'inga patikrinti:
```sql
-- Ar yra dublikatu (provider, provider_event_id)?
SELECT provider, provider_event_id, COUNT(*)
FROM payments
WHERE provider_event_id IS NOT NULL
GROUP BY provider, provider_event_id
HAVING COUNT(*) > 1;
```

---

## 6. KONFIGURACIJU PAKEITIMAI

### `.env` / `.env.staging` failai:

```bash
# V2.3 Nauji kintamieji:
ENABLE_FINANCE_METRICS=false
FINANCE_METRICS_MAX_SSE_CONNECTIONS=10
FINANCE_METRICS_RATE_LIMIT_PER_MIN=30

# V2.3 Reikia ijungti:
ENABLE_EMAIL_INTAKE=true        # Jau egzistuoja, bet default=false
ENABLE_FINANCE_LEDGER=true      # Jau egzistuoja, bet default=false
ENABLE_FINANCE_AI_INGEST=false  # Ijungti kai AI implementuotas
PII_REDACTION_ENABLED=true      # Jau ijungtas by default

# V2.3 SMS isjungimas finansu patvirtinimams:
# ENABLE_TWILIO lieka true (kitoms reikmems), bet FINAL payment
# confirmation flow naudoja email, ne SMS.
```

---

## 7. TESTU POKYTIS

### Esami testai, kuriuos reikia atnaujinti:

| Testas | Pokyciu tipas | Priezastis |
|--------|---------------|------------|
| `tests/api/test_transitions.py` | MODIFY | CERTIFIED->ACTIVE turi tikrinti client_confirmations(CONFIRMED) |
| `tests/api/test_manual_payments.py` | MODIFY | FINAL flow: SMS->Email, 409 conflict |
| `tests/api/test_webhooks.py` | MODIFY | Stripe FINAL: SMS->Email |
| `tests/test_finance_ledger.py` | MODIFY | quick-payment: row-lock, email channel, idempotency 409 |
| `tests/test_notification_outbox_unit.py` | ADD | Email confirmation queueing |
| `tests/test_audit_logs.py` | ADD | PII redaction ai_extracted_data |

### Nauji testai (sukurti):

| Testas | Kas testuojama |
|--------|----------------|
| `tests/test_v23_finance.py` | Quick-payment su row-lock, DEPOSIT idempotency (200 vs 409), FINAL->email flow, provider_event_id format validation |
| `tests/test_v23_email_confirm.py` | POST /public/confirm-payment/{token}: valid/invalid/expired/wrong-status |
| `tests/test_v23_security_404.py` | Admin IP -> 404 (ne 403), feature flag off -> 404 |
| `tests/test_v23_metrics_sse.py` | SSE endpoint: auth, 404 strategija, rate-limit, content (be PII) |
| `tests/test_v23_ai_ingest.py` | AI extract -> ai_extracted_data, confidence, proposal-only (no auto-confirm) |

---

## 8. DOKUMENTU ATNAUJINIMAI

### 8.1 `VEJAPRO_KONSTITUCIJA_V1.4.md`

**Pokyciai:**
- "SMS aktyvacija" -> "Email token aktyvacija"
- Patvirtinimu infrastruktura: `client_confirmations` (EMAIL default, ne SMS)
- Prideti: CERTIFIED->ACTIVE reikalauja `client_confirmations(CONFIRMED)` + `FINAL SUCCEEDED`

### 8.2 `VEJAPRO_TECHNINE_DOKUMENTACIJA_V1.5.md` / `V1.5.1.md`

**Pokyciai:**
- FINAL mokejimas kuria email confirmation (ne SMS)
- Aiskiai irasyti: CERTIFIED->ACTIVE reikalauja FINAL SUCCEEDED + CONFIRMED
- Payments schema: prideti `ai_extracted_data`
- `UNIQUE(provider, provider_event_id)` indeksas

### 8.3 `API_ENDPOINTS_CATALOG_V1.52.md`

**Pokyciai:**
- Pasalinti SMS kanalu aprasymus is FINAL payment flow
- Prideti: `GET /admin/finance/metrics` (SSE, ENABLE_FINANCE_METRICS, be PII)
- Prideti: `POST /public/confirm-payment/{token}` (viesas email confirmation)
- Prideti: `client_confirmations` kanalai: EMAIL (+ WHATSAPP_PING jei igyvendinta)
- Atnaujinti: quick-payment response schema (email_queued vietoj sms_queued)

### 8.4 `SCHEDULE_ENGINE_V1_SPEC.md`

**Pokyciai:**
- Patvirtinti `call_request_id` + `visit_type` apziurom (priklausomas patikslinimas)

### 8.5 Naujas dokumentas: `V2_3_CHANGELOG.md` (siuloma)

Trumpas pakeitimu sarasas deploy komandai.

---

## 9. DEPLOY CHECKLIST

```
PRE-DEPLOY:
[ ] Patikrinti ar nera (provider, provider_event_id) duplikatu DB
[ ] Backup dabartines DB
[ ] Paruosti migracija 000016

MIGRACIJA:
[ ] payments ALTER: ai_extracted_data JSONB NULL
[ ] UNIQUE (provider, provider_event_id) — po duplikatu patikrinimo
[ ] client_confirmations: channel default -> 'email'
[ ] payment_method CHECK constraint (NOT VALID + VALIDATE)

KODAS:
[ ] transition_service.py: CERTIFIED->ACTIVE tikrina client_confirmations(CONFIRMED)
[ ] finance.py: quick-payment row-lock (SELECT FOR UPDATE)
[ ] finance.py: FINAL -> email channel (ne SMS)
[ ] finance.py: DEPOSIT idempotency 409
[ ] finance.py: SSE metrics endpoint (jei ENABLE_FINANCE_METRICS=true)
[ ] projects.py: manual payment FINAL -> email (ne SMS)
[ ] projects.py: stripe webhook FINAL -> email (ne SMS)
[ ] projects.py: naujas POST /public/confirm-payment/{token}
[ ] main.py: admin IP allowlist -> 404 (ne 403)
[ ] config.py: ENABLE_FINANCE_METRICS + SSE settings
[ ] models/project.py: Payment.ai_extracted_data, ClientConfirmation channel default
[ ] schemas/finance.py: QuickPaymentResponse email_queued

SAUGUMAS:
[ ] /admin/finance/*: 404 doktrina (flag off / IP / ne admin)
[ ] AI ingest: proposal-only (jokiu auto-confirm)
[ ] SHA-256 dedupe + empty file 400 (jau veikia)
[ ] PII redagavimas audit'e ir ai_extracted_data (patikrinti)
[ ] SSE metrics: be PII, su rate limit, su 404 doktrina

AI (P1 — gali buti veliau):
[ ] finance_extract/service.py: implementuoti AI ekstrakcija
[ ] finance_extract/contracts.py: model_version
[ ] finance.py: integruoti i document extract endpoint
[ ] payments.ai_extracted_data uzpildymas

TESTAI:
[ ] Atnaujinti esamus testus (transitions, payments, webhooks)
[ ] Nauji V2.3 testai (finance, email confirm, security 404, SSE, AI ingest)

DOKUMENTACIJA:
[ ] VEJAPRO_KONSTITUCIJA_V1.4.md
[ ] VEJAPRO_TECHNINE_DOKUMENTACIJA_V1.5.md
[ ] API_ENDPOINTS_CATALOG_V1.52.md
[ ] SCHEDULE_ENGINE_V1_SPEC.md

POST-DEPLOY:
[ ] Smoke test: DEPOSIT quick-payment
[ ] Smoke test: FINAL quick-payment -> email confirmation -> ACTIVE
[ ] Smoke test: admin finance 404 (unauthorized IP)
[ ] Smoke test: idempotency (200 + 409)
[ ] Patikrinti audit_logs PII redaction
```

---

## PRIEDAS A: FAILU POKYCIO SUVESTINE

| # | Failas | Veiksmas | Eiluciu pokytis (est.) |
|---|--------|----------|------------------------|
| 1 | `migrations/versions/000016_v23_*.py` | SUKURTI | ~60 |
| 2 | `app/models/project.py` | EDIT | ~5 eilutes |
| 3 | `app/services/transition_service.py` | EDIT | ~15 eilutes |
| 4 | `app/api/v1/finance.py` | EDIT | ~120 eilutes |
| 5 | `app/api/v1/projects.py` | EDIT | ~150 eilutes |
| 6 | `app/core/config.py` | EDIT | ~15 eilutes |
| 7 | `app/main.py` | EDIT | ~5 eilutes |
| 8 | `app/schemas/finance.py` | EDIT | ~15 eilutes |
| 9 | `app/services/ai/finance_extract/service.py` | REPLACE | ~80 eilutes |
| 10 | `app/services/ai/finance_extract/contracts.py` | EDIT | ~5 eilutes |
| 11 | `tests/test_v23_finance.py` | SUKURTI | ~200 |
| 12 | `tests/test_v23_email_confirm.py` | SUKURTI | ~100 |
| 13 | `tests/test_v23_security_404.py` | SUKURTI | ~60 |
| 14 | `tests/test_v23_metrics_sse.py` | SUKURTI | ~80 |
| 15 | `tests/api/test_transitions.py` | EDIT | ~30 eilutes |
| 16 | `tests/api/test_manual_payments.py` | EDIT | ~40 eilutes |
| 17 | `tests/api/test_webhooks.py` | EDIT | ~40 eilutes |
| 18 | `tests/test_finance_ledger.py` | EDIT | ~30 eilutes |
| 19 | Dokumentacija (4 failai) | EDIT | ~100 eilutes viso |
| 20 | `.env` / `.env.staging` | EDIT | ~6 eilutes |
| | **VISO** | | **~1150 eiluciu** |

---

## PRIEDAS B: PRIKLAUSOMYBIU DIAGRAMA

```
Migracija 000016
    |
    +-> models/project.py (Payment.ai_extracted_data, UNIQUE index)
    |
    +-> config.py (ENABLE_FINANCE_METRICS)
    |
    +-> transition_service.py (CERTIFIED->ACTIVE: +client_confirmations check)
    |       |
    |       +-> finance.py (quick-payment: row-lock, email channel, 409)
    |       |       |
    |       |       +-> schemas/finance.py (response schema)
    |       |
    |       +-> projects.py (manual payment, stripe webhook: SMS->Email)
    |               |
    |               +-> Naujas endpoint: POST /public/confirm-payment/{token}
    |
    +-> main.py (404 strategija)
    |
    +-> ai/finance_extract/ (AI implementacija — P1)
    |
    +-> Testai
    |
    +-> Dokumentacija
```

**Kritinis kelias (P0):**
1. Migracija -> models -> transition_service -> finance.py + projects.py -> main.py -> testai

**Antrinis kelias (P1):**
2. AI finance extract -> metrics SSE -> papildomi testai -> dokumentacija

---

*Dokumentas sugeneruotas: 2026-02-09*
*Analize pagrista esamu kodu: V1.52 / V2.2 (commit 74182b9)*
