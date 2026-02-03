# 📋 VEJAPRO V.1.52 - Atnaujinimų Santrauka

**Data:** 2026-02-03  
**Versija:** 1.52 (iš 1.5)  
**Statusas:** 🔒 LOCKED

---



## 0. Korekcijos (2026-02-03)

?i korekcij? dalis yra kanonin? Core Domain specifikacija.

- Statusai: DRAFT, PAID, SCHEDULED, PENDING_EXPERT, CERTIFIED, ACTIVE.
- Statusas = darbo eiga; mok?jimai/aktyvacija atskirai.
- Status? keitimas tik per `/api/v1/transition-status`, forward-only, su audit log.
- is_certified privalo atitikti status in (CERTIFIED, ACTIVE).
- Marketingo vie?inimas tik jei marketing_consent=true, status >= CERTIFIED, aktorius EXPERT/ADMIN.
- Per?jimai tik: DRAFT->PAID, PAID->SCHEDULED, SCHEDULED->PENDING_EXPERT, PENDING_EXPERT->CERTIFIED, CERTIFIED->ACTIVE.
- Aktoriai: SYSTEM_STRIPE, SYSTEM_TWILIO, CLIENT, SUBCONTRACTOR, EXPERT, ADMIN.
- Deposit (payment_type=deposit) -> DRAFT->PAID. Final (payment_type=final) nekei?ia statuso, sukuria SMS patvirtinim?.
- SMS: `TAIP <KODAS>`, vienkartinis, su expires_at ir bandym? limitu.
- Kanoniniai endpointai: /projects, /projects/{id}, /transition-status, /upload-evidence, /certify-project, /webhook/stripe, /webhook/twilio, /projects/{id}/marketing-consent, /evidences/{id}/approve-for-web, /gallery.
- Audit log formatas: entity_type, entity_id, action, old_value, new_value, actor_type, actor_id, ip_address, user_agent, metadata, timestamp.
- Marketing consent neprivalomas mok?jimui; at?aukus -> show_on_web=false + audit log.
- Idempotencija: webhook'ai pagal event_id; transition-status idempotenti?kas; SMS vienkartinis.

---

## 🎯 Pagrindiniai Pakeitimai

### 1. Marketing Consent Sistema

#### DB Papildymai (`projects` lentelė)
```sql
marketing_consent   BOOLEAN NOT NULL DEFAULT FALSE,  -- sutikimas viešinti
marketing_consent_at TIMESTAMP NULL,                 -- kada duotas sutikimas
```

**Saugikliai:**
- Sutikimas duodamas sutartyje (checkbox)
- Saugoma su timestamp
- `show_on_web = true` leidžiama TIK jei `marketing_consent = TRUE`
- Audit log visiems pakeitimams

#### Naujas API Endpoint
```python
POST /projects/{id}/marketing-consent
# Atnaujina kliento sutikimą su timestamp
```

### 2. Evidences Lentelės Indeksai

**Pakeisti indeksai greičiui:**
```sql
-- Seni (pašalinti):
CREATE INDEX idx_evidences_show_on_web ON evidences(show_on_web);
CREATE INDEX idx_evidences_location_tag ON evidences(location_tag);

-- Nauji (composite indexes):
CREATE INDEX idx_evidences_gallery ON evidences(show_on_web, is_featured, uploaded_at DESC);
CREATE INDEX idx_evidences_location ON evidences(location_tag, show_on_web, uploaded_at DESC);
```

**Priežastis:** Composite indeksai daug greitesni galerijos užklausoms.

### 3. GET /gallery Cursor Pagination

**Parametrai:**
- `limit`: default 24, max 60
- `cursor`: base64 encoded timestamp
- `location_tag`: regioninis filtras
- `featured_only`: boolean

**Implementacija:**
```python
@router.get("/gallery")
async def get_gallery(
    limit: int = Query(24, le=60),
    cursor: Optional[str] = Query(None),
    location_tag: Optional[str] = None,
    featured_only: bool = False
)
```

**Response:**
```json
{
  "items": [...],
  "next_cursor": "base64_timestamp",
  "has_more": true
}
```

### 4. Marketingo Modulio Saugikliai

#### Privalomi Saugikliai (§8.6)

1. **Role-based Access:**
   - `show_on_web` gali keisti TIK `EXPERT` arba `ADMIN`

2. **Marketing Consent:**
   - `show_on_web = true` leidžiama TIK jei `marketing_consent = TRUE`

3. **Certification Status:**
   - `show_on_web = true` leidžiama TIK jei `status >= CERTIFIED`

4. **Gallery Item Structure:**
   - 1 BEFORE (`SITE_BEFORE`) + 1 AFTER (`EXPERT_CERTIFICATION`)
   - Privaloma pora iš to paties `project_id`

5. **IP Location:**
   - IP-based location TIKTAI runtime filtravimui
   - **NIEKADA nesaugoti į DB** marketingo tikslais

#### Validacijos Klasė

```python
class VejaProSafeguards:
    @staticmethod
    async def validate_certification(project_id: str):
        """≥3 nuotraukos"""
        
    @staticmethod
    async def validate_web_approval(project: Project, user: User):
        """Marketingo modulio validacija"""
        
    @staticmethod
    async def validate_gallery_item(project_id: str):
        """1 BEFORE + 1 AFTER"""
```

### 5. Sutarties Papildymas

**Paslaugų Teikimo Sutartis (→ PAID):**

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

### 6. Sprint #1 Papildymai

**Marketingo Modulis (integruota):**
- [ ] `marketing_consent` + `marketing_consent_at` laukai
- [ ] `show_on_web`, `is_featured`, `location_tag` laukai
- [ ] Composite indeksai
- [ ] GET `/gallery` su cursor pagination
- [ ] POST `/projects/{id}/marketing-consent`
- [ ] Galerijos puslapis (Next.js + before/after slider)
- [ ] Sutarties checkbox su timestamp
- [ ] Feature flag: `ENABLE_MARKETING_MODULE=false`
- [ ] Validacijos: EXPERT/ADMIN role check

### 7. Saugiklių Santrauka (§8.9)

**Naujas skyrius su visais saugikliais vienoje vietoje:**

```python
# VEJAPRO SAUGIKLIAI - PRIVALOMI
MIN_CERTIFICATION_PHOTOS = 3
TWILIO_ENABLED = True
AI_CONFIDENCE_REQUIRED = True
ROBOT_ADAPTER_MODE = "email_mock"
MARGIN_CHANGE_REQUIRES_ADMIN = True

MARKETING_SAFEGUARDS = {
    "show_on_web_roles": ["EXPERT", "ADMIN"],
    "requires_marketing_consent": True,
    "requires_certified_status": True,
    "gallery_item_structure": "1_BEFORE_1_AFTER",
    "ip_location_storage": False,
}

GALLERY_CONFIG = {
    "default_limit": 24,
    "max_limit": 60,
    "pagination_type": "cursor",
}
```

---

## Dokumentų Struktūra

```
backend/
├── README.md                                    # Navigacija
├── VEJAPRO_KONSTITUCIJA_V1.3.md                # Verslo logika
├── VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md      # V.1.52 (atnaujinta)
└── VEJAPRO_V1.52_SUMMARY.md                    # Šis failas
```

---

## Kas Pasikeitė Nuo V.1.5

| # | Pakeitimas | Skyrius | Priežastis |
|---|------------|---------|------------|
| 1 | `marketing_consent` + `marketing_consent_at` | §2.1 | Teisinis sutikimas su timestamp |
| 2 | Composite indeksai evidences | §2.1 | Greičiau galerijos užklausos |
| 3 | Cursor pagination GET /gallery | §4.1, §8.7 | Scalability (1000+ nuotraukų) |
| 4 | POST /marketing-consent endpoint | §9.5 | Sutikimo valdymas |
| 5 | Marketingo saugikliai | §8.6 | GDPR compliance + role-based |
| 6 | IP location runtime only | §8.6 | Privacy - nesaugoti DB |
| 7 | Gallery item validation | §8.6 | 1 BEFORE + 1 AFTER privaloma |
| 8 | Saugiklių santrauka | §8.9 | Centralizuota konfigūracija |
| 9 | Sutarties punktas | §9.5 | Teisinis pagrindas |
| 10 | Sprint #1 papildymai | §7, §9.8 | Integruota į MVP |

---

## 🔒 Kritiniai Saugikliai

### PRIVALOMA Patikrinti Prieš Deploy

- [ ] `marketing_consent` ir `marketing_consent_at` laukai sukurti
- [ ] Composite indeksai sukurti (ne single column)
- [ ] GET `/gallery` turi cursor pagination
- [ ] POST `/marketing-consent` endpoint veikia
- [ ] Role check: tik EXPERT/ADMIN gali keisti `show_on_web`
- [ ] Validacija: `marketing_consent = TRUE` prieš `show_on_web = true`
- [ ] Validacija: `status >= CERTIFIED` prieš `show_on_web = true`
- [ ] Gallery item turi 1 BEFORE + 1 AFTER
- [ ] IP location NESAUGOMA į DB
- [ ] Audit log visiems `marketing_consent` pakeitimams

---

## 📝 Programuotojui

### Kopijuok ir Pradėk

```bash
# 1. Atnaujinti DB schema
alembic revision -m "add_marketing_consent_v152"

# 2. Pridėti laukus
# projects: marketing_consent, marketing_consent_at
# evidences: jau turi show_on_web, is_featured, location_tag

# 3. Pakeisti indeksus
DROP INDEX idx_evidences_show_on_web;
DROP INDEX idx_evidences_location_tag;
CREATE INDEX idx_evidences_gallery ON evidences(show_on_web, is_featured, uploaded_at DESC);
CREATE INDEX idx_evidences_location ON evidences(location_tag, show_on_web, uploaded_at DESC);

# 4. Implementuoti endpoints
# POST /projects/{id}/marketing-consent
# GET /gallery (su cursor pagination)

# 5. Validacijos
# VejaProSafeguards klasė (§8.9)

# 6. Feature flag
ENABLE_MARKETING_MODULE=false
```

---

## 🎯 Sekantys Žingsniai

1. **Testuoti cursor pagination** su 100+ nuotraukų
2. **GDPR compliance review** su teisiniu
3. **Load testing** galerijos endpoint'o
4. **UI/UX testas** before/after slider
5. **Audit log monitoring** marketing_consent pakeitimams

---

## 📞 Kontaktai

- **Techniniai klausimai:** tech@vejapro.lt
- **GDPR / Teisė:** legal@vejapro.lt
- **Product:** product@vejapro.lt

---

**Dokumentą paruošė:** Tech Lead  
**Patvirtino:** Product Owner  
**Versija:** 1.52  
**Data:** 2026-02-03

© 2026 VejaPRO. Vidinė techninė dokumentacija.
