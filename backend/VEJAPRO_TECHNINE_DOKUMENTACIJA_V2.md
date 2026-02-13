# VEJAPRO TECHNINE DOKUMENTACIJA V2

**Konsoliduota V1.5 + V1.5.1 + architekturos sekcija**

**Paruosta programuotojui -- 2026-02-12**

**STATUSAS:** LOCKED / CORE DOMAIN + MARKETINGO & WEB MODULIS -- jokio improvizavimo be rastisko patvirtinimo

---

## TURINYS

A. [Sistemos Architektura](#a-sistemos-architektura)
0. [Korekcijos ir Suderinimai](#0-korekcijos-ir-suderinimai-2026-02-03)
1. [Sistemos Stuburas -- Nekintami Principai](#1-sistemos-stuburas--nekintami-principai)
2. [Duomenu Bazes Schema](#2-duomenu-bazes-schema)
3. [Statusu Perejimo Masina](#3-statusu-perejimo-masina)
4. [Kritiniai API Endpoints](#4-kritiniai-api-endpoints)
5. [AI Integracijos Taisykles](#5-ai-integracijos-taisykles)
6. [Automatizuotas Dokumentu Generavimas](#6-automatizuotas-dokumentu-generavimas)
7. [Pirmos Savaites Sprint #1](#7-pirmos-savaites-sprint-1-uzduotys)
8. [Papildomi Saugikliai](#8-papildomi-nekintami-saugikliai)
9. [Marketingo & Web Modulis](#9-marketingo--web-modulis)
10. [Testu Planas](#10-testu-planas-privalomas)

---

## A. SISTEMOS ARCHITEKTURA

### A.1 Katalogu struktura

```
backend/
├── app/
│   ├── core/           # config.py, dependencies.py
│   ├── models/         # SQLAlchemy models
│   ├── routers/        # API endpoints (projects, finance, schedule, etc.)
│   ├── schemas/        # Pydantic schemas
│   ├── services/       # Business logic (transition_service, intake_service, etc.)
│   ├── utils/          # Helpers (alerting, sms, email, resize_image)
│   ├── static/         # HTML/JS/CSS (landing, admin, portals)
│   └── migrations/     # Alembic migrations
├── tests/              # pytest tests
├── alembic.ini
└── requirements.txt
```

### A.2 Uzklausos srautas

```
Klientas -> Nginx -> FastAPI (uvicorn :8000) -> Router -> Service -> SQLAlchemy -> PostgreSQL
                                                   |
                                              Audit Log
                                                   |
                                          Notification Outbox
```

### A.3 Key Patterns lentele

| Pattern | Kur | Paaiskinimas |
|---------|-----|-------------|
| Forward-only state machine | `transition_service.py::ALLOWED_TRANSITIONS` | Statusai keiciasi tik pirmyn |
| RBAC per transition | `transition_service.py::_is_allowed_actor` | Kiekvienas perejimas turi leistimu aktoriu sarasa |
| Audit log privalomas | `transition_service.py::create_audit_log` | Kiekvienas veiksmas audituojamas su PII redakcija |
| Feature flag gating | `core/config.py` + `main.py` | Isjungtas modulis grazina 404 |
| Idempotencija | `UNIQUE(provider, provider_event_id)` | Payments, webhooks -- pakartotiniai calls safe |
| PII redakcija | `transition_service.py::_redact_pii` | Audit log nesaugo asmens duomenu |
| Notification outbox | `notification_outbox` lentele | Asinchroniniai pranesimai su retry |

### A.4 "NEKEISK be butinybes" taisykles

1. Nepridek naujo statuso be Konstitucijos atnaujinimo
2. Nekeisk `ALLOWED_TRANSITIONS` be Konstitucijos atnaujinimo
3. Nepaleisk `apply_transition()` be audit log
4. Nenaudok tiesioginio `project.status = "..."` -- tik per `apply_transition()`
5. Naujas endpoint VISADA su feature flag guard
6. Admin endpointai PRIVALO tureti role check
7. Isjungtas modulis grazina 404, ne 403

---

## 0. KOREKCIJOS IR SUDERINIMAI (2026-02-03)

Si dalis yra kanonine Core Domain specifikacija. Jei randamas konfliktas, galioja si dalis.

1. Statusai: DRAFT, PAID, SCHEDULED, PENDING_EXPERT, CERTIFIED, ACTIVE.
2. Statusas = darbo eiga. Mokejimai/aktyvacija atskirai (payments, flags).
3. Statusas keiciamas tik per POST /api/v1/transition-status, forward-only, su audit log.
4. is_certified privalo atitikti status in (CERTIFIED, ACTIVE).
5. Marketingo viesinimas tik jei marketing_consent=true, status >= CERTIFIED, aktorius EXPERT/ADMIN.
6. Perejimai tik: DRAFT->PAID, PAID->SCHEDULED, SCHEDULED->PENDING_EXPERT, PENDING_EXPERT->CERTIFIED, CERTIFIED->ACTIVE.
7. Aktoriai: SYSTEM_STRIPE, SYSTEM_TWILIO, SYSTEM_EMAIL, CLIENT, SUBCONTRACTOR, EXPERT, ADMIN. Leidimai kaip nurodyta zemiau.
8. Deposit (payment_type=deposit) -> DRAFT->PAID. Final (payment_type=final) nekeincia statuso, sukuria email patvirtinima (V2.3 default) arba SMS patvirtinima (legacy).
9. Patvirtinimo formatas: email -- vienkartinis token su expires_at (V2.3 default); SMS -- TAIP <KODAS>, vienkartinis, su expires_at, bandymu limitu (legacy).
10. Kanoniniai endpointai: /projects, /projects/{id}, /transition-status, /upload-evidence, /certify-project, /webhook/stripe, /webhook/twilio, /projects/{id}/marketing-consent, /evidences/{id}/approve-for-web, /gallery, /projects/{project_id}/payments/manual, /admin/projects/{project_id}/payments/deposit-waive, /public/confirm-payment/{token}.
11. Audit log formatas: entity_type, entity_id, action, old_value, new_value, actor_type, actor_id, ip_address, user_agent, metadata, timestamp.
12. Marketing consent neprivalomas mokejimui; atsaukus -> show_on_web=false + audit log.
13. Idempotencija: webhook'ai pagal event_id; transition-status idempotentiskas jei new_status==current_status; SMS vienkartinis; manual payments per provider_event_id.

---
## 1. SISTEMOS STUBURAS -- NEKINTAMI PRINCIPAI

### Raudonos Linijos (NIEKADA NEKEISTI)

#### 1.1 Vienos Tiesos Saltinis
```
FastAPI Backend (PostgreSQL arba Supabase)
         |
    VIENINTELIS
    TIESOS SALTINIS
         |
Frontend (Web + PWA) ir AI
    TIK SKAITO / RODO
```

#### 1.2 Frontend Apribojimai
- NIEKADA neraso verslo logikos
- NIEKADA neskaiciuoja kainu
- NIEKADA nekeicia statuso
- TIK rodo duomenis
- TIK siucia uzklausas i API

#### 1.3 Statusu Kontrole
```python
# VIENINTELIS budas keisti statusa:
POST /transition-status
```
- Griezta validacija
- Audit log privalomas
- State machine patikra

#### 1.4 Kainu ir Marzu Valdymas
- Keiciama TIK per admin panele
- PRIVALOMAS audit log
- DRAUDZIAMA keisti tiesiogiai DB

#### 1.5 Feature Flags
```python
# .env failas
ENABLE_VISION_AI=false
ENABLE_ROBOT_ADAPTER=false
ENABLE_RECURRING_JOBS=false
ENABLE_MARKETING_MODULE=false
ENABLE_MANUAL_PAYMENTS=true
ENABLE_STRIPE=false
ENABLE_TWILIO=true
RATE_LIMIT_API_ENABLED=true
SUPABASE_JWT_AUDIENCE=authenticated
SUPABASE_ANON_KEY=           # Legacy JWT anon raktas (eyJ...) Supabase Auth API
PUBLIC_BASE_URL=https://vejapro.lt  # Magic link bazinis URL
EXPOSE_ERROR_DETAILS=false
ENABLE_ADMIN_OPS_V1=false
```
- Privalomi visiems Lygio 2+ moduliams
- Pagal nutylejima: `false`
- Aktyvuojama tik po stabilumo patvirtinimo

Pastabos:
- `ENABLE_STRIPE=false` reiskia, kad Stripe admin ir webhook endpointai gali buti isjungti, bet schema ir kodas palaiko Stripe ateiciai.
- Twilio paliekamas kaip aktyvavimo patvirtinimo kanalas (kol kas).
- `RATE_LIMIT_API_ENABLED=true` ijungia IP rate limit visiems `/api/v1/*` endpointams (isskyrus webhook'us).
- `SUPABASE_JWT_AUDIENCE` naudojamas JWT `aud` validacijai ir vidiniu JWT generavimui.
- `SUPABASE_ANON_KEY` — legacy JWT formato anon raktas (eyJ...), naudojamas Supabase Auth API. Reikalingas kai `SUPABASE_KEY` yra `sb_publishable_*` formato.
- `PUBLIC_BASE_URL` — viesas bazinis URL kliento prieigos magic link emailams.
- `EXPOSE_ERROR_DETAILS=false` slepia vidines 5xx klaidu detales klientui (vis tiek loguojama serveryje).
- `ENABLE_ADMIN_OPS_V1=false` ijungia Admin Ops planner/inbox/client-card puslapius (`/admin`, `/admin/project/{id}`, `/admin/client/{key}`, `/admin/archive`).

#### 1.6 Duomenu Bazes Pakeitimai
- JOKIO "greito pataisymo" DB rankomis
- VISKAS per migracijas
- VISKAS per audit log

#### 1.7 Kliento Patirtis
```
Kiekvienas zingsnis <= 2 mygtuku
         +
SMS grandine po kiekvieno statuso
         |
    Twilio integracija
```

#### 1.8 Marketingo Principas
```
"Social Proof" automatizacija
         |
Sertifikuotos vejos automatiskai tampa galerijos dalimi
         |
    Su AISKIM klientu sutikimu
         |
marketing_consent = TRUE + timestamp
```

**Saugikliai:**
- Sutikimas duodamas sutartyje (checkbox)
- Saugoma `projects.marketing_consent` + `marketing_consent_at`
- `show_on_web = true` leidziama TIK jei `marketing_consent = TRUE`
- Tik EXPERT arba ADMIN gali keisti `show_on_web`

---

## 2. DUOMENU BAZES SCHEMA

### 2.1 Pagrindines Lenteles

#### `projects` - Projektu Lentele

```sql

CREATE TABLE projects (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_info         JSONB NOT NULL,
    status              VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
    -- DRAFT, PAID, SCHEDULED, PENDING_EXPERT, CERTIFIED, ACTIVE

    area_m2             DECIMAL(10,2),
    total_price_client  DECIMAL(12,2),  -- rodoma klientui
    internal_cost       DECIMAL(12,2),  -- mokama rangovui

    vision_analysis     JSONB,
    -- {
    --   "piktzoles": "vidutinis kiekis",
    --   "confidence": "medium",
    --   "generated_by_ai": true,
    --   "model": "mistral-7b-instruct",
    --   "timestamp": "2026-02-02T21:16:00Z"
    -- }

    has_robot           BOOLEAN DEFAULT FALSE,
    is_certified        BOOLEAN DEFAULT FALSE,
    marketing_consent   BOOLEAN NOT NULL DEFAULT FALSE,  -- sutikimas viesinti nuotraukas galerijoje
    marketing_consent_at TIMESTAMP NULL,                 -- kada duotas sutikimas
    status_changed_at   TIMESTAMP DEFAULT NOW(),
    assigned_contractor_id UUID REFERENCES users(id),
    assigned_expert_id  UUID REFERENCES users(id),
    scheduled_for       TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW(),

    CONSTRAINT chk_marketing_consent_at
        CHECK (marketing_consent = FALSE OR marketing_consent_at IS NOT NULL),
    CONSTRAINT chk_is_certified
        CHECK (
            (is_certified = TRUE AND status IN ('CERTIFIED','ACTIVE')) OR
            (is_certified = FALSE AND status NOT IN ('CERTIFIED','ACTIVE'))
        )
);

-- Indeksai
CREATE INDEX idx_projects_status ON projects(status);
CREATE INDEX idx_projects_created_at ON projects(created_at DESC);
CREATE INDEX idx_projects_is_certified ON projects(is_certified);

```

#### `audit_logs` - Audit Log Lentele (PRIVALOMA)

```sql

CREATE TABLE audit_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(50) NOT NULL,
    entity_id   UUID NOT NULL,
    action      VARCHAR(64) NOT NULL,
    old_value   JSONB,
    new_value   JSONB,
    actor_type  VARCHAR(50) NOT NULL,
    actor_id    UUID,
    ip_address  INET,
    user_agent  TEXT,
    metadata    JSONB,
    timestamp   TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_audit_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_timestamp ON audit_logs(timestamp DESC);
CREATE INDEX idx_audit_action ON audit_logs(action);

```

#### `evidences` - Nuotraukos ir Failai (papildyta Marketingo modulio laukais)

```sql
CREATE TABLE evidences (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID REFERENCES projects(id) ON DELETE CASCADE,
    file_url        TEXT NOT NULL,
    category        VARCHAR(32) NOT NULL,
    -- SITE_BEFORE, WORK_IN_PROGRESS, EXPERT_CERTIFICATION

    uploaded_by     UUID,
    uploaded_at     TIMESTAMP DEFAULT NOW(),

    -- Marketingo & Web modulis
    show_on_web     BOOLEAN DEFAULT FALSE,     -- viesinimas galerijoje (tik eksperto patvirtinta)
    is_featured     BOOLEAN DEFAULT FALSE,     -- featured pagrindiniame puslapyje
    location_tag    VARCHAR(128)               -- pvz., "Vilniaus raj." -- regioninis filtras
);

-- Indeksai
CREATE INDEX idx_evidences_project ON evidences(project_id);
CREATE INDEX idx_evidences_category ON evidences(category);
CREATE INDEX idx_evidences_gallery ON evidences(show_on_web, is_featured, uploaded_at DESC);
CREATE INDEX idx_evidences_location ON evidences(location_tag, show_on_web, uploaded_at DESC);
```

### 2.2 Papildomos Lenteles

#### `users` - Vartotojai

```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    phone           VARCHAR(20),
    role            VARCHAR(32) NOT NULL,
    -- CLIENT, SUBCONTRACTOR, EXPERT, ADMIN

    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
```

#### `margins` - Marzos Konfiguracija

```sql

CREATE TABLE margins (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_type    VARCHAR(64) NOT NULL,
    margin_percent  DECIMAL(5,2) NOT NULL,
    valid_from      TIMESTAMP DEFAULT NOW(),
    valid_until     TIMESTAMP,
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_margins_service ON margins(service_type);
CREATE INDEX idx_margins_valid ON margins(valid_from, valid_until);
CREATE UNIQUE INDEX idx_margins_active ON margins(service_type) WHERE valid_until IS NULL;

```

#### `payments` - Mokejimu Istorija (PRIVALOMA)

```sql
CREATE TABLE payments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID REFERENCES projects(id) ON DELETE CASCADE,
    provider            VARCHAR(32) NOT NULL DEFAULT 'stripe',
    provider_intent_id  VARCHAR(128),
    provider_event_id   VARCHAR(128),
    amount              DECIMAL(12,2) NOT NULL,
    currency            VARCHAR(10) NOT NULL,
    payment_type        VARCHAR(32) NOT NULL,  -- DEPOSIT, FINAL, REFUND
    status              VARCHAR(32) NOT NULL,  -- PENDING, SUCCEEDED, FAILED, REFUNDED, CHARGEBACK
    raw_payload         JSONB,
    created_at          TIMESTAMP DEFAULT NOW(),

    -- V1.5.1 papildymai: manual mokejimu kontekstas
    payment_method      VARCHAR(32) NULL,      -- pvz. CASH, BANK_TRANSFER, STRIPE, WAIVED
    received_at         TIMESTAMPTZ NULL,
    collected_by        UUID NULL REFERENCES users(id),
    collection_context  VARCHAR(32) NULL,      -- pvz. ON_SITE_AFTER_WORK, ON_SITE_BEFORE_WORK, REMOTE, OFFICE
    receipt_no          VARCHAR(64) NULL,
    proof_url           TEXT NULL,
    is_manual_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    confirmed_by        UUID NULL REFERENCES users(id),
    confirmed_at        TIMESTAMPTZ NULL,

    -- V2.3 papildymai
    ai_extracted_data   JSONB NULL             -- AI iskviecimo proposal (admin review, niekada auto-confirm)
);

CREATE UNIQUE INDEX idx_payments_event ON payments(provider, provider_event_id);
CREATE INDEX idx_payments_project ON payments(project_id);
```

Idempotencija:
- manual: `(provider='manual', provider_event_id)` (unikalus) remiasi esamu unikaliu indeksu `idx_payments_event (provider, provider_event_id)`.
- papildomai (neprivaloma): `uniq_payments_manual_receipt` ant `(provider, receipt_no)` tik kai `provider='manual' AND receipt_no IS NOT NULL`.

#### `sms_confirmations` - SMS Patvirtinimai (PRIVALOMA)

```sql
CREATE TABLE sms_confirmations (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID REFERENCES projects(id) ON DELETE CASCADE,
    token_hash              TEXT NOT NULL,
    expires_at              TIMESTAMP NOT NULL,
    confirmed_at            TIMESTAMP NULL,
    confirmed_from_phone    VARCHAR(20),
    status                  VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    attempts                INTEGER NOT NULL DEFAULT 0,
    created_at              TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_sms_project ON sms_confirmations(project_id);
CREATE INDEX idx_sms_token_hash ON sms_confirmations(token_hash);
```

#### `client_confirmations` - Kliento Patvirtinimai (V2.3)

```sql
CREATE TABLE client_confirmations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID REFERENCES projects(id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    confirmed_at    TIMESTAMPTZ NULL,
    channel         VARCHAR(32) NOT NULL DEFAULT 'email',  -- sms, email, whatsapp
    status          VARCHAR(32) NOT NULL DEFAULT 'PENDING', -- PENDING, CONFIRMED, EXPIRED
    attempts        INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_client_confirmations_project ON client_confirmations(project_id);
CREATE INDEX idx_client_confirmations_token ON client_confirmations(token_hash);
```

---

## 3. STATUSU PEREJIMO MASINA

### 3.1 Backend Validacija (PRIVALOMA)

```python
from enum import Enum
from fastapi import HTTPException

class ProjectStatus(str, Enum):
    DRAFT            = "DRAFT"
    PAID             = "PAID"
    SCHEDULED        = "SCHEDULED"
    PENDING_EXPERT   = "PENDING_EXPERT"
    CERTIFIED        = "CERTIFIED"
    ACTIVE           = "ACTIVE"

ALLOWED_TRANSITIONS = {
    ProjectStatus.DRAFT:            [ProjectStatus.PAID],
    ProjectStatus.PAID:             [ProjectStatus.SCHEDULED],
    ProjectStatus.SCHEDULED:        [ProjectStatus.PENDING_EXPERT],
    ProjectStatus.PENDING_EXPERT:   [ProjectStatus.CERTIFIED],
    ProjectStatus.CERTIFIED:        [ProjectStatus.ACTIVE],
    ProjectStatus.ACTIVE:           []  # Galutinis statusas
}

def validate_transition(current: ProjectStatus, new: ProjectStatus):
    """
    Validuoja ar statusu perejimas leidziamas.
    Kelia HTTPException jei negalimas.
    """
    if new not in ALLOWED_TRANSITIONS.get(current, []):
        raise HTTPException(
            status_code=400,
            detail=f"Negalimas perejimas: {current} -> {new}"
        )
```

### 3.2 Statusu Perejimo Endpoint

```python

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class TransitionRequest(BaseModel):
    project_id: str
    new_status: ProjectStatus
    metadata: dict = {}

@router.post("/transition-status")
async def transition_status(
    request: TransitionRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user)
):
    # 1. Gauti projekta
    project = await get_project(request.project_id)

    # 2. Validuoti perejima
    validate_transition(project.status, request.new_status)

    # 3. Issaugoti sena statusa audit log'ui
    old_status = project.status

    # 4. Atnaujinti statusa
    project.status = request.new_status
    project.status_changed_at = datetime.utcnow()
    await project.save()

    # 5. Audit log (strukturinis JSONB)

    await create_audit_log(
        entity_type="project",
        entity_id=project.id,
        action="STATUS_CHANGE",
        old_value={"status": old_status},
        new_value={"status": project.status},
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=http_request.client.host,
        user_agent=http_request.headers.get("user-agent"),
        metadata=request.metadata
    )

    # 6. Siusti SMS/email pranesima klientui
    await send_sms_notification(project, request.new_status)

    return {
        "success": True,
        "project_id": request.project_id,
        "old_status": old_status,
        "new_status": request.new_status,
        "timestamp": datetime.utcnow().isoformat()
    }

```

### 3.3 DRAFT -> PAID validacijos papildymas

Kai `new_status='PAID'` ir projektas `DRAFT`, backend privalo rasti `DEPOSIT` mokejima (manual arba stripe). Jei neranda -- `400`.

Deposit patikra:
- `payment_type='DEPOSIT'`
- `status='SUCCEEDED'`
- `provider IN ('manual','stripe')`
- arba `amount > 0` (realus inasas)
- arba `amount = 0` ir `payment_method='WAIVED'` (ADMIN atidejo inasa, pasitikime klientu)

### 3.4 RBAC Perejimu Matrica (PRIVALOMA)

| Perejimas | Kas gali inicijuoti | Triggeris |
|-----------|----------------------|-----------|
| DRAFT -> PAID | SYSTEM_STRIPE / SUBCONTRACTOR / ADMIN | Stripe deposit webhook arba manual mokejimas (su deposit payment irodymu DB) |
| PAID -> SCHEDULED | SUBCONTRACTOR / ADMIN | Rangovo priemimas arba admin patvirtinimas |
| SCHEDULED -> PENDING_EXPERT | SUBCONTRACTOR / ADMIN | Darbu uzbaigimas |
| PENDING_EXPERT -> CERTIFIED | EXPERT / ADMIN | Sertifikavimas (>=3 foto + checklist) |
| CERTIFIED -> ACTIVE | SYSTEM_TWILIO / SYSTEM_EMAIL | SMS patvirtinimas (legacy) arba email patvirtinimas (V2.3 default) + final mokejimas |

---

## 4. KRITINIAI API ENDPOINTS

Visi endpointai turi bazini prefiksa `/api/v1`.

**Pilnas esamu endpointu katalogas (gyvas, pagal koda):** `API_ENDPOINTS_CATALOG.md` (įskaitant § 2.8 Client UI V3).

### 4.1 Prioritetu Lentele

| Prioritetas | Endpoint | Metodas | Aprasymas | Validacija / Trigger |
|-------------|----------|---------|-----------|---------------------|
| **1** | `/projects` | POST | Sukurti DRAFT projekta | client_info only (photos via /upload-evidence) |
| **1** | `/projects/{id}` | GET | Grazinti pilna projekto busena | Auth check |
| **1** | `/transition-status` | POST | Vienintelis budas keisti statusa | State machine + audit log |
| **2** | `/upload-evidence` | POST | Nuotrauku kelimas | Auth + category |
| **2** | `/certify-project` | POST | Eksperto sertifikavimas | len(photos) >= 3 |
| **3** | `/projects/{id}/certificate` | GET | Generuoti PDF sertifikata | status in (CERTIFIED, ACTIVE) |
| **3** | `/webhook/stripe`, `/webhook/twilio` | POST | Stripe/Twilio webhooks | signature check |
| **3** | `/projects/{project_id}/payments/manual` | POST | Manual mokejimo fakto registravimas | ADMIN + idempotencija |
| **3** | `/admin/projects/{project_id}/payments/deposit-waive` | POST | Inaso atidejimas (waive) | ADMIN + DRAFT projektas |
| **3** | `/public/confirm-payment/{token}` | POST | Email patvirtinimo endpointas (V2.3) | Valid token + FINAL payment |
| **4** | `/gallery` | GET | Grazinti patvirtintas nuotraukas | show_on_web = true, limit=24 default (max 60), cursor pagination, filtras pagal location_tag / is_featured |

### 4.2 Endpoint Implementacijos

#### POST /projects - Projekto Kurimas

```python
class CreateProjectRequest(BaseModel):
    client_info: dict
    area_m2: float | None = None

@router.post("/projects")
async def create_project(request: CreateProjectRequest):
    # 1. Validuoti client_info
    validate_client_info(request.client_info)

    # 2. Sukurti projekta
    project = await Project.create(
        client_info=request.client_info,
        status=ProjectStatus.DRAFT,
        area_m2=request.area_m2
    )

    # 3. Audit log
    await create_audit_log(
        entity_type="project",
        entity_id=project.id,
        action="PROJECT_CREATED",
        new_value=project.status,
        actor_type="SYSTEM",
        actor_id="SYSTEM"
    )

    return {
        "project_id": str(project.id),
        "status": project.status,
        "created_at": project.created_at.isoformat()
    }
```

#### GET /projects/{id} - Projekto Informacija

**Access control (privaloma):**
- CLIENT: mato tik savo projektus
- SUBCONTRACTOR: mato tik priskirtus projektus
- EXPERT: mato tik priskirtus projektus
- ADMIN: mato visus

**Pseudokodas:**
```
if user.role == 'ADMIN': allow
elif user.role == 'CLIENT' and project.client_id == user.id: allow
elif user.role in ['SUBCONTRACTOR','EXPERT'] and project.assigned_{role}_id == user.id: allow
else: deny
```


```python
@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    project = await Project.get(project_id)

    if not project:
        raise HTTPException(404, "Projektas nerastas")

    # Gauti audit log
    audit_logs = await AuditLog.filter(
        entity_type="project",
        entity_id=project_id
    ).order_by("-timestamp")

    # Gauti nuotraukas
    evidences = await Evidence.filter(project_id=project_id)

    return {
        "project": project.dict(),
        "audit_logs": [log.dict() for log in audit_logs],
        "evidences": [ev.dict() for ev in evidences]
    }
```

#### POST /upload-evidence - Nuotrauku Ikelimas

```python
from fastapi import UploadFile, File

class EvidenceCategory(str, Enum):
    SITE_BEFORE = "SITE_BEFORE"
    WORK_IN_PROGRESS = "WORK_IN_PROGRESS"
    EXPERT_CERTIFICATION = "EXPERT_CERTIFICATION"

@router.post("/upload-evidence")
async def upload_evidence(
    project_id: str,
    category: EvidenceCategory,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    # 1. Validuoti projekta
    project = await Project.get(project_id)
    if not project:
        raise HTTPException(404, "Projektas nerastas")

    # 2. Ikelti i S3/Storage
    file_url = await upload_to_storage(file, project_id)

    # 3. Sukurti evidence irasa
    evidence = await Evidence.create(
        project_id=project_id,
        file_url=file_url,
        category=category,
        uploaded_by=current_user.id
    )

    # 4. Jei Vision AI ijungta - analizuoti
    if settings.ENABLE_VISION_AI and category == "SITE_BEFORE":
        analysis = await analyze_site(file_url)
        project.vision_analysis = analysis
        await project.save()

    return {
        "evidence_id": str(evidence.id),
        "file_url": file_url,
        "category": category
    }
```

#### POST /certify-project - Sertifikavimas

```python

class CertifyRequest(BaseModel):
    project_id: str
    checklist: dict
    notes: str = ""

@router.post("/certify-project")
async def certify_project(
    request: CertifyRequest,
    current_user: User = Depends(get_current_expert)  # Tik ekspertai
):
    # 1. Gauti projekta
    project = await Project.get(request.project_id)

    # 2. Patikrinti statusa
    if project.status != ProjectStatus.PENDING_EXPERT:
        raise HTTPException(400, "Projektas dar neparuostas sertifikavimui")

    # 3. SAUGIKLIS: Patikrinti nuotraukas
    cert_photos = await Evidence.filter(
        project_id=request.project_id,
        category="EXPERT_CERTIFICATION"
    ).count()

    if cert_photos < 3:
        raise HTTPException(400, f"Reikalingos min. 3 nuotraukos. Ikelta: {cert_photos}")

    # 4. Pereiti i CERTIFIED
    await transition_service.apply(project, ProjectStatus.CERTIFIED, actor=current_user)

    # 5. Pazymeti kaip sertifikuota
    project.is_certified = True
    await project.save()

    return {
        "success": True,
        "project_status": ProjectStatus.CERTIFIED
    }

```

#### POST /webhook/stripe - Stripe Webhook

```python

import stripe

@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    # 1. Validuoti Stripe signature
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    event = stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )

    # 2. Idempotency: ignoruoti jau apdorotus event_id
    if await PaymentEvent.exists(event.id):
        return {"received": True}

    # 3. Apdoroti tik reikalingus event'us
    if event.type == "payment_intent.succeeded":
        project_id = event.data.object.metadata.get("project_id")
        payment_type = event.data.object.metadata.get("payment_type")  # DEPOSIT/FINAL

        # 4. Grazinti klaida jei project_id neegzistuoja
        project = await Project.get(project_id)
        if not project:
            raise HTTPException(404, "Projektas nerastas")

        # 5. Deposit -> PAID (tik jei status DRAFT)
        if payment_type == "DEPOSIT" and project.status == ProjectStatus.DRAFT:
            await transition_service.apply(project, ProjectStatus.PAID, actor="system:stripe_webhook")

        # 6. Final mokejimas leidziamas tik po CERTIFIED
        if payment_type == "FINAL" and project.status not in [ProjectStatus.CERTIFIED, ProjectStatus.ACTIVE]:
            raise HTTPException(400, "Projektas dar nesertifikuotas")

        # 7. Final mokejimas nekeincia project_status; fiksuojamas payments lenteleje
        await Payments.create_from_stripe(event.data.object)

    return {"received": True}

```

#### POST /projects/{project_id}/payments/manual - Manual Mokejimo Faktas

```python
@router.post("/projects/{project_id}/payments/manual")
async def record_manual_payment(
    project_id: str,
    request: ManualPaymentRequest,
    current_user: User = Depends(require_admin)  # Tik ADMIN
):
    """
    Registruoja manual mokejimo fakta.
    Idempotentiskas per provider_event_id.
    Nekeincia projekto statuso.
    """
    # 1. Idempotencija: tikrinti ar jau yra toks provider_event_id
    existing = await Payment.filter(
        provider="manual",
        provider_event_id=request.provider_event_id
    ).first()
    if existing:
        return {"success": True, "idempotent": True, "payment_id": str(existing.id)}

    # 2. Irasyti i payments
    payment = await Payment.create(
        project_id=project_id,
        provider="manual",
        provider_event_id=request.provider_event_id,
        amount=request.amount,
        currency=request.currency,
        payment_type=request.payment_type,
        status="SUCCEEDED",
        payment_method=request.payment_method,
        received_at=request.received_at,
        collected_by=current_user.id,
        collection_context=request.collection_context,
        receipt_no=request.receipt_no,
        proof_url=request.proof_url,
        is_manual_confirmed=True,
        confirmed_by=current_user.id,
        confirmed_at=datetime.utcnow()
    )

    # 3. Audit log
    await create_audit_log(
        entity_type="payment",
        entity_id=str(payment.id),
        action="PAYMENT_RECORDED_MANUAL",
        new_value=payment.dict(),
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=request.client.host,
        metadata={"notes": request.notes}
    )

    return {"success": True, "payment_id": str(payment.id)}
```

Request pavyzdys:
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

#### POST /admin/projects/{project_id}/payments/deposit-waive - Inaso Atidejimas

```python
@router.post("/admin/projects/{project_id}/payments/deposit-waive")
async def waive_deposit(
    project_id: str,
    request: DepositWaiveRequest,
    current_user: User = Depends(require_admin)  # Tik ADMIN
):
    """
    Admin atideda pradini inasa (pasitikime klientu).
    Sukuria DEPOSIT fakta su amount=0, payment_method='WAIVED'.
    Leidziama tik DRAFT projektams.
    """
    project = await Project.get(project_id)
    if project.status != ProjectStatus.DRAFT:
        raise HTTPException(400, "Inaso atidejimas galimas tik DRAFT projektams")

    # Idempotencija
    existing = await Payment.filter(
        provider="manual",
        provider_event_id=request.provider_event_id
    ).first()
    if existing:
        return {"success": True, "idempotent": True, "payment_id": str(existing.id)}

    payment = await Payment.create(
        project_id=project_id,
        provider="manual",
        provider_event_id=request.provider_event_id,
        amount=0,
        currency=request.currency,
        payment_type="DEPOSIT",
        status="SUCCEEDED",
        payment_method="WAIVED",
        is_manual_confirmed=True,
        confirmed_by=current_user.id,
        confirmed_at=datetime.utcnow()
    )

    # Audit: payment
    await create_audit_log(
        entity_type="payment",
        entity_id=str(payment.id),
        action="PAYMENT_RECORDED_MANUAL",
        new_value=payment.dict(),
        actor_type=current_user.role,
        actor_id=current_user.id
    )

    # Audit: project
    await create_audit_log(
        entity_type="project",
        entity_id=project_id,
        action="DEPOSIT_WAIVED",
        new_value={"waived": True},
        actor_type=current_user.role,
        actor_id=current_user.id,
        metadata={"notes": request.notes}
    )

    return {"success": True, "payment_id": str(payment.id)}
```

Request pavyzdys:
```json
{
  "provider_event_id": "WAIVE-2026-000001",
  "currency": "EUR",
  "notes": "Pasitikime klientu"
}
```

---

## 5. AI INTEGRACIJOS TAISYKLES

### 5.1 M3 Modulis - Grieztos Taisykles

#### Stack
```python
# requirements.txt
langchain==0.1.0
groq==0.4.0
pillow==10.2.0
```

**Modeliai (2026 m. rekomenduojami):**
- **Mistral-7B-Instruct** - greiciausias
- **Llama-3.1-8B** - pigiausias
- Groq API - 10x greiciau nei OpenAI

#### Funkcija: analyze_site()

```python
from langchain_groq import ChatGroq
from langchain.schema import HumanMessage
import base64

async def analyze_site(image_url: str) -> dict:
    """
    Analizuoja sklypo nuotrauka su AI.

    SVARBU:
    - Grazina TIK JSON
    - NIEKADA neraso i DB
    - Visada prideda generated_by_ai: true
    """

    # 1. Atsisiusti nuotrauka
    image_data = await download_image(image_url)

    # 2. Groq AI uzklausa
    llm = ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0.1
    )

    prompt = """
    Analizuok si sklypo vaizda ir grazink JSON:
    {
        "area_estimate_m2": <skaicius>,
        "piktzoles": "mazai/vidutiniskai/daug",
        "obstacles": ["medis", "tvora", ...],
        "terrain_quality": "geras/vidutinis/prastas",
        "confidence": "low/medium/high"
    }
    """

    response = await llm.ainvoke([
        HumanMessage(content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": image_url}
        ])
    ])

    # 3. Parse JSON
    analysis = json.loads(response.content)

    # 4. PRIVALOMA: Prideti AI zyma
    analysis["generated_by_ai"] = True
    analysis["model"] = "llama-3.1-8b-instant"
    analysis["timestamp"] = datetime.utcnow().isoformat()

    return analysis
```

### 5.2 AI Apribojimai

```python
# DRAUDZIAMA
def ai_certify_project(project_id):
    # AI NEGALI keisti statuso
    project.status = "CERTIFIED"  # NIEKADA!

def ai_set_price(project_id, price):
    # AI NEGALI nustatyti kainos
    project.total_price_client = price  # NIEKADA!

# LEIDZIAMA
def ai_suggest_price(area_m2, obstacles):
    # AI gali tik SIULYTI
    return {
        "suggested_price": calculate_estimate(area_m2),
        "confidence": "medium",
        "generated_by_ai": True
    }
```

### 5.3 UI Rodymas

```typescript
// Frontend VISADA rodo AI disclaimer
interface AIAnalysis {
  area_estimate_m2: number;
  confidence: 'low' | 'medium' | 'high';
  generated_by_ai: boolean;
}

function displayAIAnalysis(analysis: AIAnalysis) {
  return (
    <div className="ai-analysis">
      <Badge variant="warning">
        AI analize (preliminari)
      </Badge>
      <p>Plotas: {analysis.area_estimate_m2} m2</p>
      <ConfidenceBadge level={analysis.confidence} />
    </div>
  );
}
```

---

## 6. AUTOMATIZUOTAS DOKUMENTU GENERAVIMAS

### 6.1 Dokumentu Lentele

| Dokumentas | Triggeris | Turinys (dinamiskai) | Saugiklis / Pastaba | Saugykla ir pristatymas |
|------------|-----------|---------------------|-------------------|------------------------|
| **Paslaugu Teikimo Sutartis** | -> PAID | client_info, kaina, plotas, darbu pabaiga + **sutikimo punktas** | Generuojama tik po Stripe/manual webhook patvirtinimo | S3 + SMS/Email nuoroda |
| **Rangos Sutartis** | -> SCHEDULED | Objektas, reikalavimai, internal_cost, terminas | Punktas: "Apmokejimas tik po sertifikavimo" | S3 + WhatsApp/Email subrangovui |
| **VejaPro Sertifikatas** | -> CERTIFIED | Nr. VP-2026-XXXX, balai, garantija 1 m., QR | Generuojamas tik po eksperto patvirtinimo + >=3 foto | S3 + SMS su QR kodu |

### 6.2 Implementacija

```python
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import qrcode

async def generate_certificate(project: Project) -> str:
    """
    Generuoja PDF sertifikata.

    SAUGIKLIS: Veikia tik jei project.is_certified == True
    """
    if not project.is_certified:
        raise ValueError("Projektas dar nesertifikuotas")

    # 1. Sukurti PDF
    cert_number = f"VP-2026-{project.id[:8].upper()}"
    filename = f"certificate_{cert_number}.pdf"

    c = canvas.Canvas(filename, pagesize=A4)

    # 2. Prideti turini
    c.setFont("Helvetica-Bold", 24)
    c.drawString(100, 750, "VejaPRO Sertifikatas")

    c.setFont("Helvetica", 12)
    c.drawString(100, 700, f"Sertifikato Nr.: {cert_number}")
    c.drawString(100, 680, f"Klientas: {project.client_info['name']}")
    c.drawString(100, 660, f"Adresas: {project.client_info['address']}")
    c.drawString(100, 640, f"Plotas: {project.area_m2} m2")
    c.drawString(100, 620, f"Garantija: 12 menesiu")

    # 3. QR kodas
    qr = qrcode.make(f"https://vejapro.lt/verify/{cert_number}")
    qr.save(f"qr_{cert_number}.png")
    c.drawImage(f"qr_{cert_number}.png", 400, 600, 100, 100)

    c.save()

    # 4. Ikelti i S3
    cert_url = await upload_to_s3(filename, "certificates")

    # 5. Siusti SMS su nuoroda
    await send_sms(
        project.client_info['phone'],
        f"Jusu VejaPRO sertifikatas paruostas: {cert_url}"
    )

    return cert_url
```

### 6.3 FINAL mokejimas ir patvirtinimo inicijavimas (V2.3 -- email-first)

Kai uzregistruojamas `payment_type='FINAL'` (manual arba stripe) ir projektas yra `CERTIFIED`:
- backend sukuria patvirtinimo request (`client_confirmations` lentele, `PENDING`, `channel='email'`) ir enqueue email per `notification_outbox`,
- statuso nekeincia; statusa pakeis tik:
  - `POST /api/v1/public/confirm-payment/{token}` (email, `SYSTEM_EMAIL`) -- **default V2.3**, arba
  - Twilio webhook po "TAIP <KODAS>" (SMS, `SYSTEM_TWILIO`) -- legacy.

CERTIFIED -> ACTIVE reikalauja ABU salygu:
- `client_confirmations` su `status='CONFIRMED'`
- `payments` su `payment_type='FINAL'`, `status='SUCCEEDED'`

Svarbu:
- `client_confirmations` lentele palaiko kanalus: `sms`, `email`, `whatsapp`.
- Email patvirtinimo endpointas (`POST /api/v1/public/confirm-payment/{token}`) naudoja `SYSTEM_EMAIL` aktoriaus tipa.
- Patvirtinimo endpointas tikrina, kad `FINAL` mokejimas yra uzregistruotas (pries aktyvuojant).

---

## 7. PIRMOS SAVAITES SPRINT #1 UZDUOTYS

> **PASTABA (2026-02-11):** Sis skyrius yra istorinis — visi Sprint #1 taskai igyvendinti.
> Dabartini statusą žr. `STATUS.md`. Katalogu struktura žr. `backend/README.md` (sekcija 2.1).

### 7.1 Prioritetu Sarasas (Programuotojui)

#### Diena 1-2: Setup
- [x] FastAPI projekto struktura
- [x] Supabase/PostgreSQL prisijungimas
- [x] Alembic migracijos setup
- [x] `.env` konfiguracija

#### Diena 3-4: Core Domain
- [x] Auth sistema (role-based): CLIENT, SUBCONTRACTOR, EXPERT, ADMIN
- [x] DB lenteles: `projects`, `audit_logs`, `evidences`, `users`
- [x] Migracijos (16 migraciju applied)

#### Diena 5-7: API Endpoints
- [x] `POST /projects`
- [x] `GET /projects/{id}`
- [x] `POST /transition-status` su state machine + audit log
- [x] Feature flags `.env`

#### Bonus: Admin Dashboard
- [x] Admin UI marzoms redaguoti
- [x] Audit log perziura
- [x] Projektu sarasas

#### Sprint Papildymas: Marketingo Modulis
- [x] `marketing_consent` ir `marketing_consent_at` laukai
- [x] `show_on_web`, `is_featured`, `location_tag` laukai
- [x] Indeksai: `idx_evidences_gallery`, `idx_evidences_location`
- [x] GET `/gallery` endpoint'as su cursor pagination
- [x] Feature flag: `ENABLE_MARKETING_MODULE=false`

### 7.2 Greitas startas

> **PASTABA:** Sis skyrius istorinis. Dabartines instrukcijos: `backend/README.md` (sekcija 1).

---

## 8. PAPILDOMI NEKINTAMI SAUGIKLIAI

### 8.1 Sertifikavimo Saugiklis

**PRIVALOMA:** Sertifikavimas galimas TIK jei >=3 nuotraukos kategorijoje EXPERT_CERTIFICATION

```python
# IRASYTI I README / KONFIGURACIJA
MIN_CERTIFICATION_PHOTOS = 3

async def validate_certification_photos(project_id: str):
    """
    Sertifikavimas galimas TIK jei >=3 nuotraukos
    kategorijoje EXPERT_CERTIFICATION
    """
    count = await Evidence.filter(
        project_id=project_id,
        category="EXPERT_CERTIFICATION"
    ).count()

    if count < MIN_CERTIFICATION_PHOTOS:
        raise HTTPException(
            400,
            f"Reikalingos min. {MIN_CERTIFICATION_PHOTOS} nuotraukos. "
            f"Ikelta: {count}"
        )
```

### 8.2 SMS Grandine

```python
from twilio.rest import Client

async def send_sms_notification(project: Project, new_status: str):
    """
    Klientas gauna SMS po KIEKVIENO statuso perejimo
    """
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    messages = {
        "PAID": "VejaPRO: Jusu uzsakymas patvirtintas! Sutartis: {contract_url}",
        "SCHEDULED": "VejaPRO: Rangovas paskirtas. Darbai prasides {date}",
        "PENDING_EXPERT": "VejaPRO: Darbai baigti. Laukiama eksperto vizito",
        "CERTIFIED": "VejaPRO: Darbai sertifikuoti! Sertifikatas: {cert_url}",
        "ACTIVE": "VejaPRO: Garantinis servisas aktyvuotas!"
    }

    message = messages.get(new_status, "VejaPRO: Statuso atnaujinimas")

    await client.messages.create(
        to=project.client_info['phone'],
        from_=settings.TWILIO_PHONE_NUMBER,
        body=message
    )
```

### 8.3 Vision AI Confidence

```python
# Vision AI atsakymas PRIVALO tureti confidence lauka
class AIAnalysisResponse(BaseModel):
    area_estimate_m2: float
    piktzoles: str
    obstacles: List[str]
    confidence: Literal["low", "medium", "high"]  # PRIVALOMA
    generated_by_ai: bool = True
```

### 8.4 Robotu Rezervacija (Mock)

```python
# Robotu rezervacija eina per abstraktu adapter'i
# Is pradziiu -- email mock

class RobotAdapter:
    async def reserve_robot(self, project_id: str, date: str):
        if settings.ENABLE_ROBOT_ADAPTER:
            # Tikra integracija ateityje
            return await real_robot_api.reserve(project_id, date)
        else:
            # Mock: siusti email
            await send_email(
                to="robots@vejapro.lt",
                subject=f"Robot reservation for {project_id}",
                body=f"Date: {date}"
            )
            return {"status": "mock", "reserved": True}
```

### 8.5 Marzu Keitimas

```python
@router.post("/admin/margins")
async def update_margin(
    request: UpdateMarginRequest,
    current_user: User = Depends(require_admin)
):
    """
    Marzos keiciamos TIK per admin panele su audit log'u
    """
    old_margin = await Margin.get(request.margin_id)

    # Audit log PRIVALOMAS
    await create_audit_log(
        entity_type="project",
        entity_id=None,
        action="MARGIN_CHANGE",
        old_value=str(old_margin.margin_percent),
        new_value=str(request.new_margin_percent),
        actor_type=current_user.role,
        actor_id=current_user.id,
        ip_address=request.client.host
    )

    # Sukurti nauja margin irasa (versioning)
    new_margin = await Margin.create(
        service_type=old_margin.service_type,
        margin_percent=request.new_margin_percent,
        created_by=current_user.id
    )

    return {"success": True, "new_margin_id": str(new_margin.id)}
```

### 8.6 Marketingo Modulio Saugikliai

```python
# PRIVALOMI SAUGIKLIAI MARKETINGO MODULIUI

# 1. evidences.show_on_web gali keisti TIK role=EXPERT arba ADMIN
@router.post("/evidences/{evidence_id}/approve-for-web")
async def approve_evidence(
    evidence_id: str,
    current_user: User = Depends(require_expert_or_admin)
):
    # Tik ekspertai ir adminai
    if current_user.role not in ["EXPERT", "ADMIN"]:
        raise HTTPException(403, "Unauthorized")

# 2. show_on_web = true leidziama TIK jei:
#    - projects.marketing_consent = TRUE
#    - status >= CERTIFIED
def validate_web_approval(project: Project, evidence: Evidence):
    if not project.marketing_consent:
        raise HTTPException(
            400,
            "Klientas nesutiko su nuotrauku naudojimu"
        )

    if project.status not in ["CERTIFIED", "ACTIVE"]:
        raise HTTPException(
            400,
            "Projektas dar nesertifikuotas"
        )

# 3. Galerijos item = 1 BEFORE + 1 AFTER is to paties project_id
async def get_gallery_item(project_id: str):
    before = await Evidence.filter(
        project_id=project_id,
        category="SITE_BEFORE"
    ).first()

    after = await Evidence.filter(
        project_id=project_id,
        category="EXPERT_CERTIFICATION",
        show_on_web=True
    ).first()

    if not before or not after:
        return None  # Neitraukti i galerija

    return {
        "before_url": before.file_url,
        "after_url": after.file_url,
        "location_tag": after.location_tag
    }

# 4. IP pagrindu tik runtime lokacijos prielaida
# NESAUGOTI DB marketingo tikslais
async def detect_user_location_runtime(request: Request):
    """
    IP-based location TIKTAI runtime filtravimui.
    NIEKADA nesaugoti i DB.
    """
    ip = request.client.host
    # Temporary detection, ne DB
    location = await ip_to_location(ip)
    return location  # Grazinti, bet nesaugoti
```

**Pastaba:** IP lokacija nustatoma tik server-side. Kliento puseje nenaudoti treciuju saliu IP API.

### 8.7 GET /gallery Parametrai

```python
# Default limit 24, max 60, cursor pagination
@router.get("/gallery")
async def get_gallery(
    limit: int = Query(24, le=60),
    cursor: Optional[str] = Query(None),
    location_tag: Optional[str] = None,
    featured_only: bool = False
):
    """
    Cursor pagination pagal uploaded_at.
    """
    query = Evidence.filter(show_on_web=True)

    if cursor:
        # Decode cursor (base64 encoded timestamp)
        cursor_time = decode_cursor(cursor)
        query = query.filter(uploaded_at__lt=cursor_time)

    if location_tag:
        query = query.filter(location_tag=location_tag)

    if featured_only:
        query = query.filter(is_featured=True)

    evidences = await query.order_by("-uploaded_at").limit(limit + 1)

    has_more = len(evidences) > limit
    items = evidences[:limit]

    next_cursor = None
    if has_more:
        next_cursor = encode_cursor(items[-1].uploaded_at)

    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_more": has_more
    }
```

### 8.8 Kritiniu Veiksmu Logging

```python
# Visi kritiniai veiksmai log'inami (kas, kada, is kokio IP)

CRITICAL_ACTIONS = [
    "STATUS_CHANGE",
    "PRICE_UPDATE",
    "MARGIN_CHANGE",
    "CERTIFICATION",
    "PAYMENT_RECEIVED",
    "PAYMENT_RECORDED_MANUAL",
    "DEPOSIT_WAIVED"
]

async def create_audit_log(
    entity_type: str,
    entity_id: str,
    action: str,
    old_value: dict | None,
    new_value: dict | None,
    actor_type: str,
    actor_id: str | None,
    ip_address: str,
    user_agent: str | None = None,
    metadata: dict | None = None
):
    """
    Sukuria audit log irasa.
    PRIVALOMA visiems kritiniams veiksmams.
    """
    await AuditLog.create(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_value=old_value,
        new_value=new_value,
        actor_type=actor_type,
        actor_id=actor_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=metadata
    )

    # Jei kritinis veiksmas - siusti alert
    if action in CRITICAL_ACTIONS:
        await send_alert_to_admin(action, entity_id, actor_id)
```

### 8.9 Visi Saugikliai - Santrauka

**Kopijuok i README / Konfiguracija:**

```python
# VEJAPRO SAUGIKLIAI - PRIVALOMI

# 1. Sertifikavimas
MIN_CERTIFICATION_PHOTOS = 3  # >=3 EXPERT_CERTIFICATION nuotraukos

# 2. SMS po kiekvieno statuso
TWILIO_ENABLED = True

# 3. AI confidence laukas
AI_CONFIDENCE_REQUIRED = True  # low/medium/high

# 4. Robotu rezervacija
ROBOT_ADAPTER_MODE = "email_mock"  # Pradzioje mock

# 5. Marzos
MARGIN_CHANGE_REQUIRES_ADMIN = True  # Tik admin panele + audit log

# 6. Kritiniu veiksmu logging
CRITICAL_ACTIONS = [
    "STATUS_CHANGE",
    "PRICE_UPDATE",
    "MARGIN_CHANGE",
    "CERTIFICATION",
    "PAYMENT_RECEIVED",
    "PAYMENT_RECORDED_MANUAL",
    "DEPOSIT_WAIVED",
    "EVIDENCE_APPROVED_FOR_WEB"
]

# 7. Marketingo modulio saugikliai
MARKETING_SAFEGUARDS = {
    "show_on_web_roles": ["EXPERT", "ADMIN"],  # Tik sie gali keisti
    "requires_marketing_consent": True,         # marketing_consent = TRUE
    "requires_certified_status": True,          # status >= CERTIFIED
    "gallery_item_structure": "1_BEFORE_1_AFTER",  # Privaloma pora
    "ip_location_storage": False,               # NIEKADA nesaugoti DB
}

# 8. GET /gallery parametrai
GALLERY_CONFIG = {
    "default_limit": 24,
    "max_limit": 60,
    "pagination_type": "cursor",  # uploaded_at
}

# 9. Indeksai (privalomi greiciui)
REQUIRED_INDEXES = [
    "idx_evidences_gallery",      # (show_on_web, is_featured, uploaded_at DESC)
    "idx_evidences_location",     # (location_tag, show_on_web, uploaded_at DESC)
]
```

**Validacijos Funkcijos:**

```python
# Visa validacija vienoje vietoje
class VejaProSafeguards:

    @staticmethod
    async def validate_certification(project_id: str):
        """Sertifikavimas: >=3 nuotraukos"""
        count = await Evidence.filter(
            project_id=project_id,
            category="EXPERT_CERTIFICATION"
        ).count()

        if count < 3:
            raise HTTPException(400, f"Reikia min. 3 nuotrauku. Ikelta: {count}")

    @staticmethod
    async def validate_web_approval(project: Project, user: User):
        """Marketingo modulio validacija"""
        # 1. Tik EXPERT arba ADMIN
        if user.role not in ["EXPERT", "ADMIN"]:
            raise HTTPException(403, "Unauthorized")

        # 2. Klientas sutiko
        if not project.marketing_consent:
            raise HTTPException(400, "Klientas nesutiko su nuotrauku naudojimu")

        # 3. Projektas sertifikuotas
        if project.status not in ["CERTIFIED", "ACTIVE"]:
            raise HTTPException(400, "Projektas dar nesertifikuotas")

    @staticmethod
    async def validate_gallery_item(project_id: str):
        """Galerijos item: 1 BEFORE + 1 AFTER"""
        before = await Evidence.filter(
            project_id=project_id,
            category="SITE_BEFORE"
        ).first()

        after = await Evidence.filter(
            project_id=project_id,
            category="EXPERT_CERTIFICATION",
            show_on_web=True
        ).first()

        if not before or not after:
            return None

        return {"before": before, "after": after}
```

---

## 9. MARKETINGO & WEB MODULIS

### 9.1 Modulio Apzvalga

**Verte:** Kiekviena sertifikuota veja tampa automatiniu marketingo turtu -- potencialus klientai gali perziureti realius pavyzdzius per 5--10 sekundziu.

**Principas:** "Social Proof" automatizacija -- sertifikuotos vejos automatiskai tampa galerijos dalimi su klientu sutikimu.

**MVP Igyvendinimas:** 2--4 savaites, ~0.01 EUR/nuotrauka (S3 saugykla).

### 9.2 DB Papildymai

Jau itraukta i `evidences` lentele (2.1):

```sql
-- Marketingo & Web modulis
show_on_web     BOOLEAN DEFAULT FALSE,     -- viesinimas galerijoje
is_featured     BOOLEAN DEFAULT FALSE,     -- featured pagrindiniame puslapyje
location_tag    VARCHAR(128)               -- regioninis filtras
```

### 9.3 Web Dizaino Specifikacija

#### Dinamine Galerija

**Next.js Komponentas:**

```typescript
// components/Gallery.tsx
import { useState, useEffect } from 'react';
import Image from 'next/image';

interface GalleryImage {
  id: string;
  file_url: string;
  location_tag: string;
  is_featured: boolean;
  uploaded_at: string;
}

export default function Gallery() {
  const [images, setImages] = useState<GalleryImage[]>([]);
  const [filter, setFilter] = useState<string>('all');
  const [autoLocation, setAutoLocation] = useState<string>('');

  useEffect(() => {
    // Auto-filtras pagal lokacija is IP / coords
    detectUserLocation().then(location => {
      setAutoLocation(location);
      setFilter(location);
    });
  }, []);

  useEffect(() => {
    // Traukti show_on_web = TRUE nuotraukas
    fetchGalleryImages(filter).then(setImages);
  }, [filter]);

  return (
    <div className="gallery-container">
      <h2>Musu Darbai</h2>

      {/* Auto-filtras su 1 spustelejimu */}
      <div className="filter-bar">
        <button
          onClick={() => setFilter('all')}
          className={filter === 'all' ? 'active' : ''}
        >
          Visi
        </button>
        <button
          onClick={() => setFilter(autoLocation)}
          className={filter === autoLocation ? 'active' : ''}
        >
          Jusu regione ({autoLocation})
        </button>
      </div>

      {/* Galerija */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {images.map(img => (
          <GalleryCard key={img.id} image={img} />
        ))}
      </div>
    </div>
  );
}
```

#### Interaktyvus "Before/After" Slideris

**Biblioteka:** `react-before-after-slider`

```typescript
// components/BeforeAfterSlider.tsx
import { ReactCompareSlider, ReactCompareSliderImage } from 'react-compare-slider';

interface BeforeAfterProps {
  beforeUrl: string;
  afterUrl: string;
  location: string;
}

export default function BeforeAfterSlider({ beforeUrl, afterUrl, location }: BeforeAfterProps) {
  return (
    <div className="before-after-container">
      <h3>{location}</h3>
      <ReactCompareSlider
        itemOne={<ReactCompareSliderImage src={beforeUrl} alt="Pries" />}
        itemTwo={<ReactCompareSliderImage src={afterUrl} alt="Po" />}
        style={{
          height: '400px',
          width: '100%',
        }}
      />
      <div className="labels">
        <span>Pries</span>
        <span>Po</span>
      </div>
    </div>
  );
}
```

### 9.4 API Endpoint: GET /gallery

```python

from fastapi import Query
from typing import Optional

@router.get("/gallery")
async def get_gallery(
    limit: int = Query(24, le=60),
    cursor: Optional[str] = Query(None),
    location_tag: Optional[str] = None,
    featured_only: bool = False
):
    """
    Cursor pagination pagal uploaded_at.

    Filtrai:
    - location_tag: regioninis filtras (pvz., "Vilniaus raj.")
    - featured_only: tik featured nuotraukos
    - limit: default 24, max 60
    """
    query = Evidence.filter(show_on_web=True)

    if cursor:
        cursor_time = decode_cursor(cursor)
        query = query.filter(uploaded_at__lt=cursor_time)

    if location_tag:
        query = query.filter(location_tag=location_tag)

    if featured_only:
        query = query.filter(is_featured=True)

    evidences = await query.order_by("-uploaded_at").limit(limit + 1)

    has_more = len(evidences) > limit
    items = evidences[:limit]

    next_cursor = None
    if has_more:
        next_cursor = encode_cursor(items[-1].uploaded_at)

    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_more": has_more
    }

```

### 9.5 Teisinis Sutikimas

**Sutikimo atsaukimas (privaloma logika):**
- Jei `marketing_consent=false`, automatiskai vykdyti:
  - `UPDATE evidences SET show_on_web=false WHERE project_id=?`
  - Irasyti audit log su pakeistu irasu skaiciumi

**Svarbu:** marketingo sutikimas yra neprivalomas. UI NEGALI blokuoti apmokejimo ar paslaugos isigijimo.


#### Sutarties Punktas

Itraukti i **Paslaugu Teikimo Sutarti** (generuojama -> PAID):

```
$X. NUOTRAUKU NAUDOJIMAS MARKETINGO TIKSLAIS

Klientas sutinka, kad nufotografuoti objekto pokyciai (nuasmeninti)
butu naudojami VejaPro galerijoje ir marketingo medziagoje.

Nuotraukos bus naudojamos tik po eksperto sertifikavimo ir be
asmeniniu duomenu (adresas, vardas, pavarde).

[ ] Sutinku su nuotrauku naudojimu marketingo tikslais

Sutikimas irasomas i duomenu baze su timestamp:
- projects.marketing_consent = TRUE
- projects.marketing_consent_at = [timestamp]
```

**Backend Implementacija:**

```python
@router.post("/projects/{project_id}/marketing-consent")
async def update_marketing_consent(
    project_id: str,
    consent: bool,
    current_user: User = Depends(get_current_user)
):
    """
    Atnaujina kliento sutikima marketingo tikslais.
    Saugoma su timestamp.
    """
    project = await Project.get(project_id)

    project.marketing_consent = consent
    if consent:
        project.marketing_consent_at = datetime.utcnow()
    else:
        project.marketing_consent_at = None

    await project.save()

    # Audit log
    await create_audit_log(
        entity_type="project",
        entity_id=project_id,
        action="MARKETING_CONSENT_UPDATE",
        old_value=str(not consent),
        new_value=str(consent),
        actor_type=current_user.role,
        actor_id=current_user.id
    )

    return {
        "success": True,
        "marketing_consent": consent,
        "marketing_consent_at": project.marketing_consent_at
    }
```

#### Web Checkbox Implementacija

```typescript
// components/ContractAgreement.tsx
import { useState } from 'react';

export default function ContractAgreement({ onAgree }: { onAgree: (agreed: boolean) => void }) {
  const [marketingConsent, setMarketingConsent] = useState(false);

  return (
    <div className="contract-agreement">
      <h3>Sutarties Salygos</h3>

      {/* Kitos sutarties salygos... */}

      <div className="consent-section">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={marketingConsent}
            onChange={(e) => {
              setMarketingConsent(e.target.checked);
              onAgree(e.target.checked);
            }}
          />
          <span>
            Sutinku, kad mano vejos nuotraukos (nuasmenintos) butu
            naudojamos VejaPro galerijoje
          </span>
        </label>
      </div>

      <button
        disabled={isSubmitting}
        onClick={() => submitContract()}
        className="btn-primary"
      >
        Patvirtinti ir Moketi
      </button>
    </div>
  );
}
```

### 9.6 Eksperto Workflow

Po sertifikavimo, ekspertas gali pazymeti nuotraukas viesinimui:

```python
@router.post("/evidences/{evidence_id}/approve-for-web")
async def approve_evidence_for_web(
    evidence_id: str,
    location_tag: str,
    is_featured: bool = False,
    current_user: User = Depends(require_expert)
):
    """
    Ekspertas patvirtina nuotrauka viesinimui galerijoje.
    """
    evidence = await Evidence.get(evidence_id)

    # Patikrinti ar projektas sertifikuotas
    project = await Project.get(evidence.project_id)
    if not project.is_certified:
        raise HTTPException(400, "Projektas dar nesertifikuotas")

    # Patikrinti kliento sutikima
    if not project.marketing_consent:
        raise HTTPException(400, "Klientas nesutiko su nuotrauku naudojimu")

    # Patvirtinti viesinimui
    evidence.show_on_web = True
    evidence.location_tag = location_tag
    evidence.is_featured = is_featured
    await evidence.save()

    # Audit log
    await create_audit_log(
        entity_type="project",
        entity_id=project.id,
        action="EVIDENCE_APPROVED_FOR_WEB",
        new_value=f"location_tag={location_tag}, featured={is_featured}",
        actor_type="EXPERT",
        actor_id=current_user.email
    )

    return {"success": True, "evidence_id": evidence_id}
```

### 9.7 Auto-Location Detection

```typescript
// utils/locationDetection.ts
export async function detectUserLocation(): Promise<string> {
  try {
    // 1. Bandyti gauti is browser geolocation
    if (navigator.geolocation) {
      const position = await new Promise<GeolocationPosition>((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject);
      });

      const { latitude, longitude } = position.coords;

      // 2. Reverse geocoding (pvz., per Google Maps API)
      const location = await reverseGeocode(latitude, longitude);
      return location; // pvz., "Vilniaus raj."
    }
  } catch (error) {
    console.warn("Geolocation failed, falling back to IP detection");
  }

  // 3. Fallback: IP-based location
  try {
    const response = await fetch('https://ipapi.co/json/');
    const data = await response.json();
    return data.region || data.city || 'Lietuva';
  } catch {
    return 'Lietuva'; // Default
  }
}
```

### 9.8 Sprint #1 Papildymas

> **PASTABA (2026-02-11):** Visi marketingo modulio taskai igyvendinti. Zr. `STATUS.md` (Marketing/Gallery sekcija).

#### Marketingo Modulis (integruota i Sprint #1) — DONE

- [x] `marketing_consent` ir `marketing_consent_at` laukai `projects` lenteleje
- [x] `show_on_web`, `is_featured`, `location_tag` laukai `evidences` lenteleje
- [x] Indeksai: `idx_evidences_gallery`, `idx_evidences_location`
- [x] GET `/gallery` endpoint'as su cursor pagination (limit=24 default, max 60)
- [x] POST `/projects/{id}/marketing-consent` endpoint'as
- [x] Galerijos puslapis (`gallery.html`) su before/after slider
- [x] Marketingo sutikimo checkbox (su timestamp)
- [x] Feature flag: `ENABLE_MARKETING_MODULE=false`
- [x] Validacijos: tik EXPERT/ADMIN gali keisti `show_on_web`

### 9.9 Kastu Analize

| Komponentas | Kaina | Pastaba |
|-------------|-------|---------|
| S3 Storage | ~$0.023/GB/men | ~0.01 EUR/nuotrauka (2MB avg) |
| CloudFront CDN | ~$0.085/GB | Greitas delivery |
| Next.js Hosting | $0 (Vercel free tier) | MVP pakanka |
| react-compare-slider | $0 (open source) | MIT licencija |
| **Viso MVP** | **~$5-10/men** | 500-1000 nuotrauku |

### 9.10 Metrikos

Sekti sias metrikos:

```python
# Marketingo modulio metrikos
class MarketingMetrics:
    gallery_views: int           # Galerijos perziuros
    before_after_interactions: int  # Slider'io naudojimas
    location_filter_usage: int   # Regioninio filtro naudojimas
    conversion_rate: float       # Galerija -> Uzklausa
    avg_time_on_gallery: float   # Vidutinis laikas galerijoje
```

---

## 10. TESTU PLANAS (PRIVALOMAS)

### 10.1 Manual mokejimu testai

- Manual idempotencija:
  - pakartotas `provider_event_id` -> antras irasas nesukuriamas (status 200, `idempotent=true`).
- `DRAFT -> PAID`:
  - be `DEPOSIT` payment -> 400
  - su manual `DEPOSIT` (`SUCCEEDED`) -> OK
  - su `DEPOSIT` waived (`amount=0`, `payment_method='WAIVED'`) -> OK

### 10.2 FINAL + CERTIFIED testai

- manual `FINAL` sukuria email confirmation request (PENDING, `channel='email'`)
- be patvirtinimo statusas lieka `CERTIFIED`
- po email token patvirtinimo (`POST /public/confirm-payment/{token}`) statusas tampa `ACTIVE` (`SYSTEM_EMAIL`)
- legacy SMS: po "TAIP <KODAS>" statusas tampa `ACTIVE` (`SYSTEM_TWILIO`)

### 10.3 V2.3 email patvirtinimo testai

- valid token -> 200, `success=true`
- invalid token -> 404
- already confirmed -> 200, `already_confirmed=true`
- email intake disabled -> 404

---

## REKOMENDACIJA PROGRAMUOTOJUI

> **PASTABA (2026-02-11):** Stuburas pastatytas ir veikia production. Zr. `backend/README.md` (greitas startas) ir `STATUS.md` (dabartinis statusas).

Pagrindiniai principai (nekinta):
- Kol Lygis 1 nestabilus — visi kiti moduliai isjungti per feature flags.
- Klientas negaista laiko: kiekvienas zingsnis <= 2 mygtuku.
- Pries darydamas bet kokius pakeitimus — **VISADA** patikrink Konstitucija.

---

## GALUTINIS PRIMINIMAS

### NIEKADA NEKEISTI:

1. Statusu perejimu be validacijos
2. Kainu be audit log
3. AI sprendimu be zmogaus patvirtinimo
4. DB pakeitimu be migraciju
5. Feature'u be flags

### VISADA DARYTI:

1. Audit log kritiniams veiksmams
2. SMS/email po kiekvieno statuso
3. Validacija state machine
4. Auth check visiems endpoints
5. Error handling su aiskiais pranesimais

---

**Dokumenta patvirtino:** Tech Lead
**Data:** 2026-02-11
**Versija:** 2.0
**Statusas:** LOCKED

(c) 2026 VejaPRO. Vidine technine dokumentacija.

---

## PAPILDOMI GENERAVIMO PAVYZDZIAI

Jei reikia, galiu sugeneruoti:

1. **Pilna POST /transition-status endpoint'o koda** (su validacija ir audit log'u)
2. **PDF generavimo pavyzdi** (ReportLab / WeasyPrint) su sablonu
3. **Mermaid sekos diagrama** visam ciklui
4. **Alembic migracijos faila** su lentelemis

---

## Versiju istorija

| Versija | Data | Pakeitimai |
|---------|------|-----------|
| V1.5 | 2026-02-03 | Pradine technine dokumentacija su marketingo moduliu |
| V1.5.1 | 2026-02-07 | Payments-first patch, manual mokejimai, RBAC atnaujinimas |
| V2 | 2026-02-09 | Konsoliduota V1.5+V1.5.1, prideta architekturos sekcija, V2.3 email patvirtinimas |
| V2.6.1 | 2026-02-10 | Addendum: Admin UI V3 (shared design system + Klientu modulis) — zr. `backend/docs/ADMIN_UI_V3.md` |
| V2.6.3 | 2026-02-11 | Dokumentacijos apzvalga: Sprint #1 ir 9.8 pazymeti kaip DONE (istoriniai), sutrumpinta 7.2 sekcija |
| V2.7.2 | 2026-02-12 | Addendum: dev-friendly admin auth modelis (`/login` opt-in, `/api/v1/auth/refresh`, dual token storage) |
| V2.8 | 2026-02-12 | Admin UI V5.1 konsolidacija (shared CSS komponentai, vienodas cache-busting), email sablonu centralizacija (`email_templates.py`) |
| V2.9 | 2026-02-12 | Admin UI V5.3 funkcionalumo fix: auth flow (token secret, Supabase detection), form auto-styling CSS, auth checks 7 puslapiuose, kalendoriaus `<details>`, LT vertimai, graceful empty states |

---

## Addendum: Admin UI V3 (2026-02-10)

Sis addendum dokumentuoja Admin UI V3 redesign (UI lygmuo). Core domain (statusu masina, payments-first, V2.3 aktyvacija) nelieciamas.

Kanoninis dokumentas:
- `backend/docs/ADMIN_UI_V3.md`

Pagrindiniai implementacijos failai:
- `backend/app/static/admin-shared.css`
- `backend/app/static/admin-shared.js`
- `backend/app/static/admin.html`
- `backend/app/static/customers.html`
- `backend/app/static/customer-profile.html`
- `backend/app/static/projects.html`
- `backend/app/static/admin-projects.js`
- `backend/app/api/v1/admin_customers.py`
- `backend/app/api/v1/admin_dashboard.py`
- `backend/app/api/v1/admin_project_details.py`

**Client UI V3 (kliento portalas):** backend-driven view modeliai, vienas pagrindinis veiksmas per projekto view, estimate/services/action endpointai. Katalogas: `API_ENDPOINTS_CATALOG.md` § 2.8. Pilna specifikacija: `backend/docs/CLIENT_UI_V3.md`. Implementacija: `backend/app/api/v1/client_views.py`, `backend/app/static/client.html`.

---

## Addendum: Admin Auth (2026-02-13, V3.2)

Sis addendum papildo Admin UI V3 dokumentacija autentifikacijos lygyje.

Pagrindiniai principai:
- **Topbar puslapiai**: login-only auth per `/login`. Token card pašalintas iš topbar layout. 401 klaida → automatinis redirect į `/login`.
- **Legacy sidebar** (`admin-legacy.html`): dev token kelias vis dar veikia per `initTokenCard()`.
- Supabase login: `GET /login` + `sessionStorage["vejapro_supabase_session"]` (admin) arba `sessionStorage["vejapro_client_session"]` (klientas).
- `login.js` palaiko dual-mode: `/admin` kelias → admin prisijungimas, `/client` kelias → kliento prisijungimas.
- Supabase sesijos atnaujinimas vyksta per `POST /api/v1/auth/refresh` (rotation-safe, klaidos 400/401/502).
- Frontend naudoja viena token tiesa: `Auth.getToken()` (sessionStorage pirma, localStorage fallback).

Backend JWT verifikacija (V3.2):
- **Dual algorithm**: HS256 (per `SUPABASE_JWT_SECRET`) + ES256 (per JWKS iš `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`).
- Algoritmo parinkimas: pirma tikrinamas token header `alg` laukas, bandoma atitinkamas algoritmas, fallback į kitą.
- JWKS klientas cachʼinamas per procesą (thread-safe, 1h lifespan).
- `SUPABASE_ANON_KEY`: legacy JWT formato anon raktas (eyJ...), naudojamas Supabase Auth API. Jei tuščias, fallback į `SUPABASE_KEY`.
- `PUBLIC_BASE_URL`: viešas bazinis URL magic link emailams (default: `https://vejapro.lt`).

Kliento prieigos email:
- `POST /api/v1/admin/projects/{id}/send-client-access` — generuoja CLIENT JWT (HS256, 7d) ir siunčia magic link emailą.
- Magic link formatas: `{PUBLIC_BASE_URL}/client?token={jwt}&project={id}`.
- Email šablonas: `CLIENT_PORTAL_ACCESS` per `email_templates.py`.
