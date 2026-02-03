# 🔧 VEJAPRO TECHNINĖ DOKUMENTACIJA V.1.52

**Paruošta programuotojui – 2026 m. vasario pradžia**

**STATUSAS:** 🔒 **LOCKED / CORE DOMAIN + MARKETINGO & WEB MODULIS** – jokio improvizavimo be raštiško patvirtinimo

---

## 📋 TURINYS

0. [Korekcijos ir Suderinimai](#0-korekcijos-ir-suderinimai-2026-02-03)
1. [Sistemos Stuburas – Nekintami Principai](#1-sistemos-stuburas--nekintami-principai)
2. [Duomenų Bazės Schema](#2-duomenų-bazės-schema)
3. [Statusų Perėjimo Mašina](#3-statusų-perėjimo-mašina)
4. [Kritiniai API Endpoints](#4-kritiniai-api-endpoints)
5. [AI Integracijos Taisyklės](#5-ai-integracijos-taisyklės)
6. [Automatizuotas Dokumentų Generavimas](#6-automatizuotas-dokumentų-generavimas)
7. [Pirmos Savaitės Sprint #1](#7-pirmos-savaitės-sprint-1-užduotys)
8. [Papildomi Saugikliai](#8-papildomi-nekintami-saugikliai)
9. [Marketingo & Web Modulis](#9-marketingo--web-modulis)
---


## 0. KOREKCIJOS IR SUDERINIMAI (2026-02-03)

?i dalis yra kanonin? Core Domain specifikacija. Jei randamas konfliktas, galioja ?i dalis.

1. Statusai: DRAFT, PAID, SCHEDULED, PENDING_EXPERT, CERTIFIED, ACTIVE.
2. Statusas = darbo eiga. Mok?jimai/aktyvacija atskirai (payments, flags).
3. Statusas kei?iamas tik per POST /api/v1/transition-status, forward-only, su audit log.
4. is_certified privalo atitikti status in (CERTIFIED, ACTIVE).
5. Marketingo vie?inimas tik jei marketing_consent=true, status >= CERTIFIED, aktorius EXPERT/ADMIN.
6. Per?jimai tik: DRAFT->PAID, PAID->SCHEDULED, SCHEDULED->PENDING_EXPERT, PENDING_EXPERT->CERTIFIED, CERTIFIED->ACTIVE.
7. Aktoriai: SYSTEM_STRIPE, SYSTEM_TWILIO, CLIENT, SUBCONTRACTOR, EXPERT, ADMIN. Leidimai kaip nurodyta ?emiau.
8. Deposit (payment_type=deposit) -> DRAFT->PAID. Final (payment_type=final) nekei?ia statuso, sukuria SMS patvirtinim?.
9. SMS formatas: TAIP <KODAS>, vienkartinis, su expires_at, bandym? limitu.
10. Kanoniniai endpointai: /projects, /projects/{id}, /transition-status, /upload-evidence, /certify-project, /webhook/stripe, /webhook/twilio, /projects/{id}/marketing-consent, /evidences/{id}/approve-for-web, /gallery.
11. Audit log formatas: entity_type, entity_id, action, old_value, new_value, actor_type, actor_id, ip_address, user_agent, metadata, timestamp.
12. Marketing consent neprivalomas mok?jimui; at?aukus -> show_on_web=false + audit log.
13. Idempotencija: webhook'ai pagal event_id; transition-status idempotenti?kas jei new_status==current_status; SMS vienkartinis.

---
## 1. SISTEMOS STUBURAS – NEKINTAMI PRINCIPAI

### 🔴 Raudonos Linijos (NIEKADA NEKEISTI)

#### 1.1 Vienos Tiesos Šaltinis
```
FastAPI Backend (PostgreSQL arba Supabase)
         ↓
    VIENINTELIS
    TIESOS ŠALTINIS
         ↓
Frontend (Web + PWA) ir AI
    TIK SKAITO / RODO
```

#### 1.2 Frontend Apribojimai
- ❌ **NIEKADA** nerašo verslo logikos
- ❌ **NIEKADA** neskaičiuoja kainų
- ❌ **NIEKADA** nekeičia statuso
- ✅ **TIK** rodo duomenis
- ✅ **TIK** siunčia užklausas į API

#### 1.3 Statusų Kontrolė
```python
# VIENINTELIS būdas keisti statusą:
POST /transition-status
```
- Griežta validacija
- Audit log privalomas
- State machine patikra

#### 1.4 Kainų ir Maržų Valdymas
- Keičiama **TIK** per admin panelę
- **PRIVALOMAS** audit log
- **DRAUDŽIAMA** keisti tiesiogiai DB

#### 1.5 Feature Flags
```python
# .env failas
ENABLE_VISION_AI=false
ENABLE_ROBOT_ADAPTER=false
ENABLE_RECURRING_JOBS=false
ENABLE_MARKETING_MODULE=false
```
- Privalomi visiems Lygio 2+ moduliams
- Pagal nutylėjimą: `false`
- Aktyvuojama tik po stabilumo patvirtinimo

#### 1.6 Duomenų Bazės Pakeitimai
- ❌ **JOKIO** "greito pataisymo" DB rankomis
- ✅ **VISKAS** per migracijas
- ✅ **VISKAS** per audit log

#### 1.7 Kliento Patirtis
```
Kiekvienas žingsnis ≤ 2 mygtukų
         +
SMS grandinė po kiekvieno statuso
         ↓
    Twilio integracija
```

#### 1.8 Marketingo Principas
```
"Social Proof" automatizacija
         ↓
Sertifikuotos vejos automatiškai tampa galerijos dalimi
         ↓
    Su AIŠKIU klientų sutikimu
         ↓
marketing_consent = TRUE + timestamp
```

**Saugikliai:**
- Sutikimas duodamas sutartyje (checkbox)
- Saugoma `projects.marketing_consent` + `marketing_consent_at`
- `show_on_web = true` leidžiama TIK jei `marketing_consent = TRUE`
- Tik EXPERT arba ADMIN gali keisti `show_on_web`

---

## 2. DUOMENŲ BAZĖS SCHEMA

### 2.1 Pagrindinės Lentelės

#### `projects` - Projektų Lentelė

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
    marketing_consent   BOOLEAN NOT NULL DEFAULT FALSE,  -- sutikimas vie?inti nuotraukas galerijoje
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

#### `audit_logs` - Audit Log Lentelė (PRIVALOMA)

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
    show_on_web     BOOLEAN DEFAULT FALSE,     -- viešinimas galerijoje (tik eksperto patvirtinta)
    is_featured     BOOLEAN DEFAULT FALSE,     -- featured pagrindiniame puslapyje
    location_tag    VARCHAR(128)               -- pvz., "Vilniaus raj." – regioninis filtras
);

-- Indeksai
CREATE INDEX idx_evidences_project ON evidences(project_id);
CREATE INDEX idx_evidences_category ON evidences(category);
CREATE INDEX idx_evidences_gallery ON evidences(show_on_web, is_featured, uploaded_at DESC);
CREATE INDEX idx_evidences_location ON evidences(location_tag, show_on_web, uploaded_at DESC);
```

### 2.2 Papildomos Lentelės

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

#### `margins` - Maržos Konfigūracija

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

#### `payments` - Mok?jim? Istorija (PRIVALOMA)

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
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_payments_event ON payments(provider, provider_event_id);
CREATE INDEX idx_payments_project ON payments(project_id);
```

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

---

## 3. STATUSŲ PERĖJIMO MAŠINA

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
    Validuoja ar statusų perėjimas leidžiamas.
    Kelia HTTPException jei negalimas.
    """
    if new not in ALLOWED_TRANSITIONS.get(current, []):
        raise HTTPException(
            status_code=400,
            detail=f"Negalimas perėjimas: {current} → {new}"
        )
```

### 3.2 Statusų Perėjimo Endpoint

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
    # 1. Gauti projekt?
    project = await get_project(request.project_id)

    # 2. Validuoti per?jim?
    validate_transition(project.status, request.new_status)

    # 3. I?saugoti sen? status? audit log'ui
    old_status = project.status

    # 4. Atnaujinti status?
    project.status = request.new_status
    project.status_changed_at = datetime.utcnow()
    await project.save()

    # 5. Audit log (strukt?rinis JSONB)
    
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

    # 6. Si?sti SMS prane?im? klientui
    await send_sms_notification(project, request.new_status)

    return {
        "success": True,
        "project_id": request.project_id,
        "old_status": old_status,
        "new_status": request.new_status,
        "timestamp": datetime.utcnow().isoformat()
    }

```




### 3.3 RBAC Per?jim? Matrica (PRIVALOMA)

| Per?jimas | Kas gali inicijuoti | Triggeris |
|-----------|----------------------|-----------|
| DRAFT -> PAID | SYSTEM_STRIPE | Stripe deposit webhook |
| PAID -> SCHEDULED | SUBCONTRACTOR / ADMIN | Rangovo pri?mimas arba admin patvirtinimas |
| SCHEDULED -> PENDING_EXPERT | SUBCONTRACTOR / ADMIN | Darb? u?baigimas |
| PENDING_EXPERT -> CERTIFIED | EXPERT / ADMIN | Sertifikavimas (>=3 foto + checklist) |
| CERTIFIED -> ACTIVE | SYSTEM_TWILIO | SMS patvirtinimas + final mok?jimas |

---

## 4. KRITINIAI API ENDPOINTS

Visi endpointai turi bazin? prefiks? `/api/v1`.

### 4.1 Prioritetų Lentelė

| Prioritetas | Endpoint | Metodas | Aprašymas | Validacija / Trigger |
|-------------|----------|---------|-----------|---------------------|
| **1** | `/projects` | POST | Sukurti DRAFT projektą | client_info only (photos via /upload-evidence) |
| **1** | `/projects/{id}` | GET | Grąžinti pilną projekto būseną | Auth check |
| **1** | `/transition-status` | POST | Vienintelis būdas keisti statusą | State machine + audit log |
| **2** | `/upload-evidence` | POST | Nuotraukų kėlimas | Auth + category |
| **2** | `/certify-project` | POST | Eksperto sertifikavimas | len(photos) ≥ 3 |
| **3** | `/projects/{id}/certificate` | GET | Generuoti PDF sertifikat? | status in (CERTIFIED, ACTIVE) |
| **3** | `/webhook/stripe`, `/webhook/twilio` | POST | Stripe/Twilio webhooks | signature check |
| **4** | `/gallery` | GET | Grąžinti patvirtintas nuotraukas | show_on_web = true, limit=24 default (max 60), cursor pagination, filtras pagal location_tag / is_featured |

### 4.2 Endpoint Implementacijos

#### POST /projects - Projekto Kūrimas

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
        actor_type=\"SYSTEM\",
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

#### POST /upload-evidence - Nuotraukų Įkėlimas

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
    # 1. Validuoti projektą
    project = await Project.get(project_id)
    if not project:
        raise HTTPException(404, "Projektas nerastas")
    
    # 2. Įkelti į S3/Storage
    file_url = await upload_to_storage(file, project_id)
    
    # 3. Sukurti evidence įrašą
    evidence = await Evidence.create(
        project_id=project_id,
        file_url=file_url,
        category=category,
        uploaded_by=current_user.id
    )
    
    # 4. Jei Vision AI įjungta - analizuoti
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
    # 1. Gauti projekt?
    project = await Project.get(request.project_id)

    # 2. Patikrinti status?
    if project.status != ProjectStatus.PENDING_EXPERT:
        raise HTTPException(400, "Projektas dar neparuo?tas sertifikavimui")

    # 3. SAUGIKLIS: Patikrinti nuotraukas
    cert_photos = await Evidence.filter(
        project_id=request.project_id,
        category="EXPERT_CERTIFICATION"
    ).count()

    if cert_photos < 3:
        raise HTTPException(400, f"Reikalingos min. 3 nuotraukos. ?kelta: {cert_photos}")
    # 4. Pereiti ? CERTIFIED
 Pereiti ? CERTIFIED
    await transition_service.apply(project, ProjectStatus.CERTIFIED, actor=current_user)

    # 6. Pa?ym?ti kaip sertifikuot?
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

        # 4. Gr??inti klaid? jei project_id neegzistuoja
        project = await Project.get(project_id)
        if not project:
            raise HTTPException(404, "Projektas nerastas")

        # 5. Deposit -> PAID (tik jei status DRAFT)
        if payment_type == "DEPOSIT" and project.status == ProjectStatus.DRAFT:
            await transition_service.apply(project, ProjectStatus.PAID, actor="system:stripe_webhook")

        # 6. Final mok?jimas leid?iamas tik po CERTIFIED
        if payment_type == "FINAL" and project.status not in [ProjectStatus.CERTIFIED, ProjectStatus.ACTIVE]:
            raise HTTPException(400, "Projektas dar nesertifikuotas")

        # 7. Final mok?jimas nekei?ia project_status; fiksuojamas payments lentel?je
        await Payments.create_from_stripe(event.data.object)

    return {"received": True}

```

---

## 5. AI INTEGRACIJOS TAISYKLĖS

### 5.1 M3 Modulis - Griežtos Taisyklės

#### Stack
```python
# requirements.txt
langchain==0.1.0
groq==0.4.0
pillow==10.2.0
```

**Modeliai (2026 m. rekomenduojami):**
- **Mistral-7B-Instruct** - greičiausias
- **Llama-3.1-8B** - pigiausias
- Groq API - 10x greičiau nei OpenAI

#### Funkcija: analyze_site()

```python
from langchain_groq import ChatGroq
from langchain.schema import HumanMessage
import base64

async def analyze_site(image_url: str) -> dict:
    """
    Analizuoja sklypo nuotrauką su AI.
    
    SVARBU: 
    - Grąžina TIK JSON
    - NIEKADA nerašo į DB
    - Visada prideda generated_by_ai: true
    """
    
    # 1. Atsisiųsti nuotrauką
    image_data = await download_image(image_url)
    
    # 2. Groq AI užklausa
    llm = ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0.1
    )
    
    prompt = """
    Analizuok šį sklypo vaizdą ir grąžink JSON:
    {
        "area_estimate_m2": <skaičius>,
        "piktzoles": "mažai/vidutiniškai/daug",
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
    
    # 4. PRIVALOMA: Pridėti AI žymą
    analysis["generated_by_ai"] = True
    analysis["model"] = "llama-3.1-8b-instant"
    analysis["timestamp"] = datetime.utcnow().isoformat()
    
    return analysis
```

### 5.2 AI Apribojimai

```python
# ❌ DRAUDŽIAMA
def ai_certify_project(project_id):
    # AI NEGALI keisti statuso
    project.status = "CERTIFIED"  # NIEKADA!

def ai_set_price(project_id, price):
    # AI NEGALI nustatyti kainos
    project.total_price_client = price  # NIEKADA!

# ✅ LEIDŽIAMA
def ai_suggest_price(area_m2, obstacles):
    # AI gali tik SIŪLYTI
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
        AI analizė (preliminari)
      </Badge>
      <p>Plotas: {analysis.area_estimate_m2} m²</p>
      <ConfidenceBadge level={analysis.confidence} />
    </div>
  );
}
```

---

## 6. AUTOMATIZUOTAS DOKUMENTŲ GENERAVIMAS

### 6.1 Dokumentų Lentelė

| Dokumentas | Triggeris | Turinys (dinamiškai) | Saugiklis / Pastaba | Saugykla ir pristatymas |
|------------|-----------|---------------------|-------------------|------------------------|
| **Paslaugų Teikimo Sutartis** | → PAID | client_info, kaina, plotas, darbų pabaiga + **sutikimo punktas** | Generuojama tik po Stripe webhook patvirtinimo | S3 + SMS/Email nuoroda |
| **Rangos Sutartis** | → SCHEDULED | Objektas, reikalavimai, internal_cost, terminas | Punktas: "Apmokėjimas tik po sertifikavimo" | S3 + WhatsApp/Email subrangovui |
| **VejaPro Sertifikatas** | → CERTIFIED | Nr. VP-2026-XXXX, balai, garantija 1 m., QR | Generuojamas tik po eksperto patvirtinimo + ≥3 foto | S3 + SMS su QR kodu |

### 6.2 Implementacija

```python
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import qrcode

async def generate_certificate(project: Project) -> str:
    """
    Generuoja PDF sertifikatą.
    
    SAUGIKLIS: Veikia tik jei project.is_certified == True
    """
    if not project.is_certified:
        raise ValueError("Projektas dar nesertifikuotas")
    
    # 1. Sukurti PDF
    cert_number = f"VP-2026-{project.id[:8].upper()}"
    filename = f"certificate_{cert_number}.pdf"
    
    c = canvas.Canvas(filename, pagesize=A4)
    
    # 2. Pridėti turinį
    c.setFont("Helvetica-Bold", 24)
    c.drawString(100, 750, "VejaPRO Sertifikatas")
    
    c.setFont("Helvetica", 12)
    c.drawString(100, 700, f"Sertifikato Nr.: {cert_number}")
    c.drawString(100, 680, f"Klientas: {project.client_info['name']}")
    c.drawString(100, 660, f"Adresas: {project.client_info['address']}")
    c.drawString(100, 640, f"Plotas: {project.area_m2} m²")
    c.drawString(100, 620, f"Garantija: 12 mėnesių")
    
    # 3. QR kodas
    qr = qrcode.make(f"https://vejapro.lt/verify/{cert_number}")
    qr.save(f"qr_{cert_number}.png")
    c.drawImage(f"qr_{cert_number}.png", 400, 600, 100, 100)
    
    c.save()
    
    # 4. Įkelti į S3
    cert_url = await upload_to_s3(filename, "certificates")
    
    # 5. Siųsti SMS su nuoroda
    await send_sms(
        project.client_info['phone'],
        f"Jūsų VejaPRO sertifikatas paruoštas: {cert_url}"
    )
    
    return cert_url
```

---

## 7. PIRMOS SAVAITĖS SPRINT #1 UŽDUOTYS

### 7.1 Prioritetų Sąrašas (Programuotojui)

#### ✅ Diena 1-2: Setup
- [ ] FastAPI projekto struktūra
- [ ] Supabase/PostgreSQL prisijungimas
- [ ] Alembic migracijos setup
- [ ] `.env` konfigūracija

```bash
# Projekto struktūra
vejapro-backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── models/
│   │   ├── project.py
│   │   ├── audit_log.py
│   │   └── evidence.py
│   ├── routers/
│   │   ├── projects.py
│   │   ├── auth.py
│   │   └── webhooks.py
│   └── services/
│       ├── state_machine.py
│       ├── ai_service.py
│       └── sms_service.py
├── alembic/
├── requirements.txt
└── .env
```

#### ✅ Diena 3-4: Core Domain
- [ ] Auth sistema (role-based)
  - CLIENT
  - SUBCONTRACTOR
  - EXPERT
  - ADMIN
- [ ] DB lentelės:
  - `projects`
  - `audit_logs`
  - `evidences`
  - `users`
- [ ] Migracijos

#### ✅ Diena 5-7: API Endpoints
- [ ] `POST /projects`
- [ ] `GET /projects/{id}`
- [ ] `POST /transition-status` su:
  - State machine validacija
  - Audit log įrašymas
- [ ] Feature flags `.env`:
  ```
  ENABLE_VISION_AI=false
  ENABLE_ROBOT_ADAPTER=false
  ```

#### ✅ Bonus: Admin Dashboard
- [ ] Paprastas admin UI maržoms redaguoti
- [ ] Audit log peržiūra
- [ ] Projektų sąrašas

#### ✅ Sprint Papildymas: Marketingo Modulis
- [ ] Pridėti `marketing_consent` ir `marketing_consent_at` laukus `projects` lentelėje
- [ ] Sukurti `show_on_web`, `is_featured`, `location_tag` laukus `evidences` lentelėje
- [ ] Sukurti indeksus: `idx_evidences_gallery`, `idx_evidences_location`
- [ ] GET `/gallery` endpoint'ą (grąžina tik `show_on_web = true` nuotraukas)
- [ ] Cursor pagination implementacija
- [ ] Feature flag: `ENABLE_MARKETING_MODULE=false`

### 7.2 Kopijuok ir Pradėk

```bash
# 1. Sukurti projektą
mkdir vejapro-backend
cd vejapro-backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Įdiegti priklausomybes
pip install fastapi uvicorn sqlalchemy alembic psycopg2-binary pydantic python-dotenv

# 3. Sukurti .env
cat > .env << EOF
DATABASE_URL=postgresql://user:pass@localhost/vejapro
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
ENABLE_VISION_AI=false
ENABLE_ROBOT_ADAPTER=false
EOF

# 4. Paleisti
uvicorn app.main:app --reload
```

---

## 8. PAPILDOMI NEKINTAMI SAUGIKLIAI

### 8.1 Sertifikavimo Saugiklis

**PRIVALOMA:** Sertifikavimas galimas TIK jei ≥3 nuotraukos kategorijoje EXPERT_CERTIFICATION

```python
# ĮRAŠYTI Į README / KONFIGŪRACIJĄ
MIN_CERTIFICATION_PHOTOS = 3

async def validate_certification_photos(project_id: str):
    """
    Sertifikavimas galimas TIK jei ≥3 nuotraukos 
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
            f"Įkelta: {count}"
        )
```

### 8.2 SMS Grandinė

```python
from twilio.rest import Client

async def send_sms_notification(project: Project, new_status: str):
    """
    Klientas gauna SMS po KIEKVIENO statuso perėjimo
    """
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    
    messages = {
        "PAID": "VejaPRO: Jūsų užsakymas patvirtintas! Sutartis: {contract_url}",
        "SCHEDULED": "VejaPRO: Rangovas paskirtas. Darbai prasidės {date}",
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
# Vision AI atsakymas PRIVALO turėti confidence lauką
class AIAnalysisResponse(BaseModel):
    area_estimate_m2: float
    piktzoles: str
    obstacles: List[str]
    confidence: Literal["low", "medium", "high"]  # PRIVALOMA
    generated_by_ai: bool = True
```

### 8.4 Robotų Rezervacija (Mock)

```python
# Robotų rezervacija eina per abstraktų adapter'į
# Iš pradžių – email mock

class RobotAdapter:
    async def reserve_robot(self, project_id: str, date: str):
        if settings.ENABLE_ROBOT_ADAPTER:
            # Tikra integracija ateityje
            return await real_robot_api.reserve(project_id, date)
        else:
            # Mock: siųsti email
            await send_email(
                to="robots@vejapro.lt",
                subject=f"Robot reservation for {project_id}",
                body=f"Date: {date}"
            )
            return {"status": "mock", "reserved": True}
```

### 8.5 Maržų Keitimas

```python
@router.post("/admin/margins")
async def update_margin(
    request: UpdateMarginRequest,
    current_user: User = Depends(require_admin)
):
    """
    Maržos keičiamos TIK per admin panelę su audit log'u
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
    
    # Sukurti naują margin įrašą (versioning)
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

# 2. show_on_web = true leidžiama TIK jei:
#    - projects.marketing_consent = TRUE
#    - status >= CERTIFIED
def validate_web_approval(project: Project, evidence: Evidence):
    if not project.marketing_consent:
        raise HTTPException(
            400, 
            "Klientas nesutiko su nuotraukų naudojimu"
        )
    
    if project.status not in ["CERTIFIED", "ACTIVE"]:
        raise HTTPException(
            400,
            "Projektas dar nesertifikuotas"
        )

# 3. Galerijos item = 1 BEFORE + 1 AFTER iš to paties project_id
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
        return None  # Neįtraukti į galeriją
    
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
    NIEKADA nesaugoti į DB.
    """
    ip = request.client.host
    # Temporary detection, ne DB
    location = await ip_to_location(ip)
    return location  # Grąžinti, bet nesaugoti
```

**Pastaba:** IP lokacija nustatoma tik server-side. Kliento pus?je nenaudoti tre?i?j? ?ali? IP API.

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

### 8.8 Kritinių Veiksmų Logging

```python
# Visi kritiniai veiksmai log'inami (kas, kada, iš kokio IP)

CRITICAL_ACTIONS = [
    "STATUS_CHANGE",
    "PRICE_UPDATE",
    "MARGIN_CHANGE",
    "CERTIFICATION",
    "PAYMENT_RECEIVED"
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
    Sukuria audit log ?ra??.
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

    # Jei kritinis veiksmas - si?sti alert
    if action in CRITICAL_ACTIONS:
        await send_alert_to_admin(action, entity_id, changed_by)
    
    # Jei kritinis veiksmas - siųsti alert
    if action in CRITICAL_ACTIONS:
        await send_alert_to_admin(action, project_id, changed_by)
```

### 8.9 Visi Saugikliai - Santrauka

**Kopijuok į README / Konfigūraciją:**

```python
# VEJAPRO SAUGIKLIAI - PRIVALOMI

# 1. Sertifikavimas
MIN_CERTIFICATION_PHOTOS = 3  # ≥3 EXPERT_CERTIFICATION nuotraukos

# 2. SMS po kiekvieno statuso
TWILIO_ENABLED = True

# 3. AI confidence laukas
AI_CONFIDENCE_REQUIRED = True  # low/medium/high

# 4. Robotų rezervacija
ROBOT_ADAPTER_MODE = "email_mock"  # Pradžioje mock

# 5. Maržos
MARGIN_CHANGE_REQUIRES_ADMIN = True  # Tik admin panelė + audit log

# 6. Kritinių veiksmų logging
CRITICAL_ACTIONS = [
    "STATUS_CHANGE",
    "PRICE_UPDATE", 
    "MARGIN_CHANGE",
    "CERTIFICATION",
    "PAYMENT_RECEIVED",
    "EVIDENCE_APPROVED_FOR_WEB"
]

# 7. Marketingo modulio saugikliai
MARKETING_SAFEGUARDS = {
    "show_on_web_roles": ["EXPERT", "ADMIN"],  # Tik šie gali keisti
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

# 9. Indeksai (privalomi greičiui)
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
        """Sertifikavimas: ≥3 nuotraukos"""
        count = await Evidence.filter(
            project_id=project_id,
            category="EXPERT_CERTIFICATION"
        ).count()
        
        if count < 3:
            raise HTTPException(400, f"Reikia min. 3 nuotraukų. Įkelta: {count}")
    
    @staticmethod
    async def validate_web_approval(project: Project, user: User):
        """Marketingo modulio validacija"""
        # 1. Tik EXPERT arba ADMIN
        if user.role not in ["EXPERT", "ADMIN"]:
            raise HTTPException(403, "Unauthorized")
        
        # 2. Klientas sutiko
        if not project.marketing_consent:
            raise HTTPException(400, "Klientas nesutiko su nuotraukų naudojimu")
        
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

### 9.1 Modulio Apžvalga

**Vertė:** Kiekviena sertifikuota veja tampa automatiniu marketingo turtu – potencialūs klientai gali peržiūrėti realius pavyzdžius per 5–10 sekundžių.

**Principas:** "Social Proof" automatizacija – sertifikuotos vejos automatiškai tampa galerijos dalimi su klientų sutikimu.

**MVP Įgyvendinimas:** 2–4 savaitės, ~0.01 €/nuotrauka (S3 saugykla).

### 9.2 DB Papildymai

Jau įtraukta į `evidences` lentelę (§2.1):

```sql
-- Marketingo & Web modulis
show_on_web     BOOLEAN DEFAULT FALSE,     -- viešinimas galerijoje
is_featured     BOOLEAN DEFAULT FALSE,     -- featured pagrindiniame puslapyje
location_tag    VARCHAR(128)               -- regioninis filtras
```

### 9.3 Web Dizaino Specifikacija

#### Dinaminė Galerija

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
    // Auto-filtras pagal lokaciją iš IP / coords
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
      <h2>Mūsų Darbai</h2>
      
      {/* Auto-filtras su 1 spustelėjimu */}
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
          📍 Jūsų regione ({autoLocation})
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
        itemOne={<ReactCompareSliderImage src={beforeUrl} alt="Prieš" />}
        itemTwo={<ReactCompareSliderImage src={afterUrl} alt="Po" />}
        style={{
          height: '400px',
          width: '100%',
        }}
      />
      <div className="labels">
        <span>← Prieš</span>
        <span>Po →</span>
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

**Sutikimo at?aukimas (privaloma logika):**
- Jei `marketing_consent=false`, automati?kai vykdyti:
  - `UPDATE evidences SET show_on_web=false WHERE project_id=?`
  - ?ra?yti audit log su pakeist? ?ra?? skai?iumi

**Svarbu:** marketingo sutikimas yra neprivalomas. UI NEGALI blokuoti apmok?jimo ar paslaugos ?sigijimo.


#### Sutarties Punktas

Įtraukti į **Paslaugų Teikimo Sutartį** (generuojamą → PAID):

```
§X. NUOTRAUKŲ NAUDOJIMAS MARKETINGO TIKSLAIS

Klientas sutinka, kad nufotografuoti objekto pokyčiai (nuasmeninti) 
būtų naudojami VejaPro galerijoje ir marketingo medžiagoje.

Nuotraukos bus naudojamos tik po eksperto sertifikavimo ir be 
asmeninių duomenų (adresas, vardas, pavardė).

☐ Sutinku su nuotraukų naudojimu marketingo tikslais

Sutikimas įrašomas į duomenų bazę su timestamp:
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
    Atnaujina kliento sutikimą marketingo tikslais.
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
      <h3>Sutarties Sąlygos</h3>
      
      {/* Kitos sutarties sąlygos... */}
      
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
            Sutinku, kad mano vejos nuotraukos (nuasmenintos) būtų 
            naudojamos VejaPro galerijoje
          </span>
        </label>
      </div>

      <button 
        disabled={isSubmitting}
        onClick={() => submitContract()}
        className="btn-primary"
      >
        Patvirtinti ir Mokėti
      </button>
    </div>
  );
}
```

### 9.6 Eksperto Workflow

Po sertifikavimo, ekspertas gali pažymėti nuotraukas viešinimui:

```python
@router.post("/evidences/{evidence_id}/approve-for-web")
async def approve_evidence_for_web(
    evidence_id: str,
    location_tag: str,
    is_featured: bool = False,
    current_user: User = Depends(require_expert)
):
    """
    Ekspertas patvirtina nuotrauką viešinimui galerijoje.
    """
    evidence = await Evidence.get(evidence_id)
    
    # Patikrinti ar projektas sertifikuotas
    project = await Project.get(evidence.project_id)
    if not project.is_certified:
        raise HTTPException(400, "Projektas dar nesertifikuotas")
    
    # Patikrinti kliento sutikimą
    # (tikrinama iš sutarties metadata)
    if not project.marketing_consent:
        raise HTTPException(400, "Klientas nesutiko su nuotraukų naudojimu")
    
    # Patvirtinti viešinimui
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
        actor_type=\"SYSTEM\",
        actor_id=current_user.email
    )
    
    return {"success": True, "evidence_id": evidence_id}
```

### 9.7 Auto-Location Detection

```typescript
// utils/locationDetection.ts
export async function detectUserLocation(): Promise<string> {
  try {
    // 1. Bandyti gauti iš browser geolocation
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

Pridėti prie [§7 Sprint #1](#7-pirmos-savaitės-sprint-1-užduotys):

#### ✅ Marketingo Modulis (integruota į Sprint #1)

- [ ] Pridėti `marketing_consent` (BOOLEAN NOT NULL DEFAULT FALSE) ir `marketing_consent_at` (TIMESTAMP NULL) į `projects` lentelę
- [ ] Sukurti `show_on_web`, `is_featured`, `location_tag` laukus `evidences` lentelėje
- [ ] Sukurti indeksus: `idx_evidences_gallery`, `idx_evidences_location`
- [ ] GET `/gallery` endpoint'ą su cursor pagination (limit=24 default, max 60)
- [ ] POST `/projects/{id}/marketing-consent` endpoint'ą
- [ ] Paprastą galerijos puslapį (Next.js) su before/after slider
- [ ] Sutarties checkbox'ą marketingo sutikimui (su timestamp)
- [ ] Feature flag: `ENABLE_MARKETING_MODULE=false`
- [ ] Validacijos: tik EXPERT/ADMIN gali keisti `show_on_web`

### 9.9 Kaštų Analizė

| Komponentas | Kaina | Pastaba |
|-------------|-------|---------|
| S3 Storage | ~$0.023/GB/mėn | ~0.01€/nuotrauka (2MB avg) |
| CloudFront CDN | ~$0.085/GB | Greitas delivery |
| Next.js Hosting | $0 (Vercel free tier) | MVP pakanka |
| react-compare-slider | $0 (open source) | MIT licencija |
| **Viso MVP** | **~$5-10/mėn** | 500-1000 nuotraukų |

### 9.10 Metrikos

Sekti šias metrikos:

```python
# Marketingo modulio metrikos
class MarketingMetrics:
    gallery_views: int           # Galerijos peržiūros
    before_after_interactions: int  # Slider'io naudojimas
    location_filter_usage: int   # Regioninio filtro naudojimas
    conversion_rate: float       # Galerija → Užklausa
    avg_time_on_gallery: float   # Vidutinis laikas galerijoje
```

---

## 📝 REKOMENDACIJA PROGRAMUOTOJUI

### Kopijuok ir Įklijuok Tiesiai

```
Pirmiausia pastatyk stuburą:

1. ✅ DB schema + migracijos
   - projects (įskaitant marketing_consent ir marketing_consent_at)
   - audit_logs
   - evidences (įskaitant show_on_web, is_featured, location_tag)
   - users
   - Indeksai greičiui (ypač idx_evidences_gallery, idx_evidences_location)

2. ✅ Statusų mašina + POST /transition-status
   - Validacija su ALLOWED_TRANSITIONS
   - Audit log įrašymas
   - SMS pranešimai

3. ✅ Auth + roles
   - CLIENT, SUBCONTRACTOR, EXPERT, ADMIN
   - JWT tokens
   - Role-based access control

4. ✅ Feature flags .env
   - ENABLE_VISION_AI=false
   - ENABLE_ROBOT_ADAPTER=false
   - ENABLE_RECURRING_JOBS=false

Kol Lygis 1 nestabilus – visi kiti moduliai išjungti per flags.

Klientas negaišta laiko:
- Kiekvienas žingsnis ≤ 2 mygtukų
- SMS grandinė po kiekvieno statuso
- Automatinis dokumentų generavimas
```

---

## 🔒 GALUTINIS PRIMINIMAS

### NIEKADA NEKEISTI:

1. ❌ Statusų perėjimų be validacijos
2. ❌ Kainų be audit log
3. ❌ AI sprendimų be žmogaus patvirtinimo
4. ❌ DB pakeitimų be migracijų
5. ❌ Feature'ų be flags

### VISADA DARYTI:

1. ✅ Audit log kritiniams veiksmams
2. ✅ SMS po kiekvieno statuso
3. ✅ Validacija state machine
4. ✅ Auth check visiems endpoints
5. ✅ Error handling su aiškiais pranešimais

---

**Dokumentą patvirtino:** Tech Lead  
**Data:** 2026-02-02  
**Versija:** 1.52  
**Statusas:** 🔒 LOCKED

© 2026 VejaPRO. Vidinė techninė dokumentacija.

---

## 📎 PAPILDOMI GENERAVIMO PAVYZDŽIAI

Jei reikia, galiu sugeneruoti:

1. **Pilną POST /transition-status endpoint'o kodą** (su validacija ir audit log'u)
2. **PDF generavimo pavyzdį** (ReportLab / WeasyPrint) su šablonu
3. **Mermaid sekos diagramą** visam ciklui
4. **Alembic migracijos failą** su lentelėmis

