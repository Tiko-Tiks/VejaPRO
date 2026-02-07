# Subrangovo ir Eksperto Portalų Dokumentacija

## Apžvalga

Sukurti du atskiri portalai subrangovams (SUBCONTRACTOR) ir ekspertams (EXPERT) su JWT autentifikacija ir role-based prieiga.

## Architektūra

### Aktoriai

**SUBCONTRACTOR (Rangovas)**
- Priskirtas projektui per `assigned_contractor_id`
- Gali keisti statusus: PAID→SCHEDULED, SCHEDULED→PENDING_EXPERT
- Gali įkelti evidence (SITE_BEFORE, WORK_IN_PROGRESS)
- Mato tik savo priskirtus projektus

**EXPERT (Ekspertas/Agronomas)**
- Priskirtas projektui per `assigned_expert_id`
- Gali keisti statusą: PENDING_EXPERT→CERTIFIED
- Gali įkelti evidence (EXPERT_CERTIFICATION)
- Turi VETO teisę - gali atmesti darbus
- Sertifikuoja projektus (min 3 nuotraukos + checklist)
- Gali approve evidence for web (`show_on_web`)

## API Endpoints

### Token Generation (Admin Only)

#### GET /api/v1/admin/users/{user_id}/contractor-token
Generuoja JWT token subrangovui (7 dienų galiojimas).

**Request:**
```bash
GET /api/v1/admin/users/{user_id}/contractor-token
Authorization: Bearer <admin_token>
```

**Response:**
```json
{
  "token": "eyJhbGc...",
  "expires_at": 1738876800,
  "user_id": "uuid"
}
```

**Validacija:**
- User role turi būti `SUBCONTRACTOR`
- Sukuria audit log su action `CONTRACTOR_TOKEN_ISSUED`

#### GET /api/v1/admin/users/{user_id}/expert-token
Generuoja JWT token ekspertui (7 dienų galiojimas).

**Request:**
```bash
GET /api/v1/admin/users/{user_id}/expert-token
Authorization: Bearer <admin_token>
```

**Response:**
```json
{
  "token": "eyJhbGc...",
  "expires_at": 1738876800,
  "user_id": "uuid"
}
```

**Validacija:**
- User role turi būti `EXPERT`
- Sukuria audit log su action `EXPERT_TOKEN_ISSUED`

### Contractor Endpoints

#### GET /api/v1/contractor/projects
Grąžina subrangovo priskirtus projektus.

**Request:**
```bash
GET /api/v1/contractor/projects?status=SCHEDULED&limit=50
Authorization: Bearer <contractor_token>
```

**Query Parameters:**
- `status` (optional) - Filtruoti pagal statusą
- `limit` (default: 50, max: 200)
- `cursor` (optional) - Pagination cursor

**Response:**
```json
{
  "items": [
    {
      "id": "uuid",
      "status": "SCHEDULED",
      "scheduled_for": "2026-02-10T10:00:00Z",
      "assigned_contractor_id": "uuid",
      "assigned_expert_id": "uuid",
      "created_at": "2026-02-06T12:00:00Z",
      "updated_at": "2026-02-06T14:00:00Z"
    }
  ],
  "next_cursor": "base64_cursor",
  "has_more": true
}
```

**Autorizacija:**
- Filtruoja projektus kur `assigned_contractor_id = current_user.id`
- Audit log prieiga tik savo projektams

### Expert Endpoints

#### GET /api/v1/expert/projects
Grąžina eksperto priskirtus projektus.

**Request:**
```bash
GET /api/v1/expert/projects?status=PENDING_EXPERT&limit=50
Authorization: Bearer <expert_token>
```

**Query Parameters:**
- `status` (optional) - Filtruoti pagal statusą
- `limit` (default: 50, max: 200)
- `cursor` (optional) - Pagination cursor

**Response:**
```json
{
  "items": [
    {
      "id": "uuid",
      "status": "PENDING_EXPERT",
      "scheduled_for": "2026-02-10T10:00:00Z",
      "assigned_contractor_id": "uuid",
      "assigned_expert_id": "uuid",
      "created_at": "2026-02-06T12:00:00Z",
      "updated_at": "2026-02-06T14:00:00Z"
    }
  ],
  "next_cursor": "base64_cursor",
  "has_more": true
}
```

**Autorizacija:**
- Filtruoja projektus kur `assigned_expert_id = current_user.id`
- Audit log prieiga tik savo projektams

## UI Portalai

### Contractor Portal

**URL:** `/contractor`

**Funkcionalumas:**
- JWT autentifikacija (localStorage)
- Projektų sąrašas su filtravimo tabs
- Statistikos dashboard (viso/suplanuoti/vykdomi/baigti)
- Projekto detalių modal
- Status badges su spalvomis
- Responsive dizainas

**Filtrai:**
- Visi
- Apmokėti (PAID)
- Suplanuoti (SCHEDULED)
- Laukia Eksperto (PENDING_EXPERT)

**Statistika:**
- Viso Projektų
- Suplanuoti (SCHEDULED)
- Vykdomi (PENDING_EXPERT)
- Baigti (CERTIFIED + ACTIVE)

### Expert Portal

**URL:** `/expert`

**Funkcionalumas:**
- JWT autentifikacija (localStorage)
- Projektų sąrašas su filtravimo tabs
- Statistikos dashboard (viso/laukia/sertifikuota/aktyvūs)
- Sertifikavimo modal su checklist
- Evidence grid su nuotraukomis
- VETO galimybė (atmesti projektą)
- Responsive dizainas

**Filtrai:**
- Visi
- Laukia Patikros (PENDING_EXPERT)
- Sertifikuoti (CERTIFIED)
- Aktyvūs (ACTIVE)

**Sertifikavimo Checklist:**
1. ✓ Pagrindo lygumas (nėra duobių > 2cm)
2. ✓ Sėjos tolygumas (≥80% ploto)
3. ✓ Kraštų apdirbimas
4. ✓ Roboto bazės stabilumas
5. ✓ Perimetro kabelio vientisumas
6. ✓ Sklypo švara

**Statistika:**
- Viso Projektų
- Laukia Patikros (PENDING_EXPERT)
- Sertifikuota (CERTIFIED)
- Aktyvūs (ACTIVE)

## Autentifikacija

### JWT Token Struktūra

**Contractor Token:**
```json
{
  "sub": "user_id",
  "email": "contractor@example.com",
  "app_metadata": {
    "role": "SUBCONTRACTOR"
  },
  "iat": 1738790400,
  "exp": 1739395200
}
```

**Expert Token:**
```json
{
  "sub": "user_id",
  "email": "expert@example.com",
  "app_metadata": {
    "role": "EXPERT"
  },
  "iat": 1738790400,
  "exp": 1739395200
}
```

### Token Galiojimas
- **TTL:** 168 valandos (7 dienos)
- **Storage:** `expert.html` naudoja `sessionStorage`; `contractor.html` naudoja `localStorage` (`vejapro_contractor_token`)
- **Refresh:** Automatinis logout po 401 response

### Security Headers
- Portalai pateikiami su `no-store` cache headers (autentifikuotas turinys)
- Token siunčiamas per `Authorization: Bearer <token>` header
- Auto-logout jei 401 Unauthorized
- `expert.html` naudoja DOM-safe rendering (be innerHTML) ir `sessionStorage`
- XSS apsauga: `contractor.html` — pašalinti inline onclick, UUID sanitizavimas, addEventListener pattern
- XSS apsauga: `margins.html` — escape funkcija naudotojo duomenims
- Cache: `/contractor` ir `/expert` dabar naudoja `_client_headers()` (Cache-Control: no-store)

## Admin Workflow

### 1. Sukurti User su Role

```sql
INSERT INTO users (email, phone, role, is_active)
VALUES ('contractor@example.com', '+37060000000', 'SUBCONTRACTOR', true);

INSERT INTO users (email, phone, role, is_active)
VALUES ('expert@example.com', '+37060000001', 'EXPERT', true);
```

### 2. Priskirti Projektui

**Admin UI arba API:**
```bash
# Assign contractor
POST /api/v1/admin/projects/{project_id}/assign-contractor
{
  "user_id": "contractor_uuid"
}

# Assign expert
POST /api/v1/admin/projects/{project_id}/assign-expert
{
  "user_id": "expert_uuid"
}
```

### 3. Generuoti Token

**Admin UI arba API:**
```bash
# Contractor token
GET /api/v1/admin/users/{user_id}/contractor-token

# Expert token
GET /api/v1/admin/users/{user_id}/expert-token
```

### 4. Perduoti Token

- Nukopijuoti JWT token
- Išsiųsti subrangovui/ekspertui (email, SMS, secure channel)
- Jie įveda token į portalą

## Statusų Perėjimai

### Contractor Permissions

| Iš Statuso | Į Statusą | Leidžiama |
|------------|-----------|-----------|
| PAID | SCHEDULED | ✅ |
| SCHEDULED | PENDING_EXPERT | ✅ |
| Kiti | - | ❌ |

### Expert Permissions

| Iš Statuso | Į Statusą | Leidžiama |
|------------|-----------|-----------|
| PENDING_EXPERT | CERTIFIED | ✅ (su checklist) |
| PENDING_EXPERT | PENDING_EXPERT | ✅ (VETO) |
| Kiti | - | ❌ |

## Evidence Upload

### Contractor Evidence Categories
- `SITE_BEFORE` - Sklypo nuotraukos prieš darbus
- `WORK_IN_PROGRESS` - Darbų eigos nuotraukos

### Expert Evidence Categories
- `EXPERT_CERTIFICATION` - Sertifikavimo nuotraukos (min 3)

### Upload Endpoint
```bash
POST /api/v1/upload-evidence
Content-Type: multipart/form-data
Authorization: Bearer <token>

project_id: uuid
category: SITE_BEFORE | WORK_IN_PROGRESS | EXPERT_CERTIFICATION
file: [binary]
```

## Sertifikavimo Workflow

### 1. Rangovas Baigia Darbus
- Statusas: SCHEDULED
- Įkelia min. 3 nuotraukas (WORK_IN_PROGRESS)
- Pereina į PENDING_EXPERT

### 2. Ekspertas Gauna Pranešimą
- Mato projektą savo portale
- Filtras: "Laukia Patikros"

### 3. Ekspertas Tikrina
- Atidaro projekto modal
- Peržiūri nuotraukas
- Užpildo checklist (6 punktai)
- Įveda pastabas

### 4. Sprendimas

**Sertifikuoti:**
```bash
POST /api/v1/certify-project
{
  "project_id": "uuid",
  "checklist": {
    "ground": true,
    "seed": true,
    "edges": true,
    "robot": true,
    "perimeter": true,
    "cleanliness": true
  },
  "notes": "Darbai atlikti kokybiškai"
}
```
- Statusas: PENDING_EXPERT → CERTIFIED
- Sukuria audit log
- Generuoja sertifikatą

**Atmesti (VETO):**
- Įveda atmetimo priežastį
- Statusas lieka PENDING_EXPERT
- Rangovas turi taisyti

## Audit Log

### Tracked Actions

**Contractor:**
- `CONTRACTOR_TOKEN_ISSUED` - Token generavimas
- `STATUS_CHANGE` - Statusų keitimas
- `UPLOAD_EVIDENCE` - Evidence įkėlimas

**Expert:**
- `EXPERT_TOKEN_ISSUED` - Token generavimas
- `STATUS_CHANGE` - Statusų keitimas (CERTIFIED)
- `UPLOAD_EVIDENCE` - Evidence įkėlimas
- `EVIDENCE_APPROVED` - Evidence patvirtinimas web
- `PROJECT_CERTIFIED` - Projekto sertifikavimas
- `PROJECT_REJECTED` - Projekto atmetimas (VETO)

### Audit Log Prieiga

**Contractor:**
- Mato tik savo priskirtų projektų audit logs
- Filtruojama per `assigned_contractor_id`

**Expert:**
- Mato tik savo priskirtų projektų audit logs
- Filtruojama per `assigned_expert_id`

## Testing

### Manual Testing Checklist

**Contractor Portal:**
- [ ] JWT autentifikacija veikia
- [ ] Projektų sąrašas rodo tik priskirtus projektus
- [ ] Filtrai veikia (PAID, SCHEDULED, PENDING_EXPERT)
- [ ] Statistika atnaujinama
- [ ] Projekto modal atidaro detalės
- [ ] Logout išvalo token

**Expert Portal:**
- [ ] JWT autentifikacija veikia
- [ ] Projektų sąrašas rodo tik priskirtus projektus
- [ ] Filtrai veikia (PENDING_EXPERT, CERTIFIED, ACTIVE)
- [ ] Statistika atnaujinama
- [ ] Sertifikavimo modal rodo checklist
- [ ] Evidence grid rodo nuotraukas
- [ ] Sertifikavimas veikia (visi checklist punktai)
- [ ] Logout išvalo token

### API Testing

```bash
# 1. Admin sukuria contractor token
curl -X GET "http://localhost:8000/api/v1/admin/users/{user_id}/contractor-token" \
  -H "Authorization: Bearer <admin_token>"

# 2. Contractor gauna projektus
curl -X GET "http://localhost:8000/api/v1/contractor/projects" \
  -H "Authorization: Bearer <contractor_token>"

# 3. Admin sukuria expert token
curl -X GET "http://localhost:8000/api/v1/admin/users/{user_id}/expert-token" \
  -H "Authorization: Bearer <admin_token>"

# 4. Expert gauna projektus
curl -X GET "http://localhost:8000/api/v1/expert/projects" \
  -H "Authorization: Bearer <expert_token>"

# 5. Expert sertifikuoja projektą
curl -X POST "http://localhost:8000/api/v1/certify-project" \
  -H "Authorization: Bearer <expert_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "uuid",
    "checklist": {...},
    "notes": "OK"
  }'
```

## Troubleshooting

### 401 Unauthorized
**Priežastis:** Token negaliojantis arba pasibaigęs
**Sprendimas:**
1. Patikrinti token galiojimą (exp claim)
2. Generuoti naują token per admin
3. Įvesti naują token į portalą

### 403 Forbidden
**Priežastis:** User neturi prieigos prie projekto
**Sprendimas:**
1. Patikrinti ar projektas priskirtas user (`assigned_contractor_id` / `assigned_expert_id`)
2. Admin turi priskirti projektą per `/assign-contractor` arba `/assign-expert`

### Projektų sąrašas tuščias
**Priežastis:** User neturi priskirtų projektų
**Sprendimas:**
1. Admin turi priskirti projektus per admin UI
2. Patikrinti `assigned_contractor_id` / `assigned_expert_id` DB

### Sertifikavimas nepavyksta
**Priežastis:** Trūksta evidence arba checklist neužpildytas
**Sprendimas:**
1. Patikrinti ar projektas turi min. 3 evidence (EXPERT_CERTIFICATION)
2. Patikrinti ar visi checklist punktai pažymėti
3. Patikrinti ar projekto statusas yra PENDING_EXPERT

## Future Enhancements

### Planned Features
- [ ] Evidence upload UI contractor/expert portaluose
- [ ] Real-time notifications (WebSocket)
- [ ] Mobile app (React Native)
- [ ] Offline mode su sync
- [ ] Evidence comments/annotations
- [ ] Project timeline visualization
- [ ] Export reports (PDF)
- [x] Pilna lietuvių lokalizacija (2026-02-07)
- ✅ Responsive dizainas — visi portalai turi @media queries (768px), touch targets (44px)

### Performance Improvements
- [ ] Redis cache projektų sąrašams
- [ ] Pagination optimization
- [ ] Image thumbnails
- [ ] Lazy loading

---

**Last Updated:** 2026-02-07  
**Status:** ✅ Production Ready  
**Kalba:** Visa UI lietuvių kalba (lang="lt")  
**Maintainer:** VejaPRO Development Team
