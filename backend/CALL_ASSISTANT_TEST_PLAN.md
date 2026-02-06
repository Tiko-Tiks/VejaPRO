# Call Assistant Testavimo Planas

## Apžvalga
Call Assistant funkcionalumas leidžia klientams palikti skambučių užklausas per landing puslapį ir administratoriams valdyti jas per Admin UI.

## Staging Aplinka
- **URL:** `https://staging.vejapro.lt`
- **Feature flag:** `ENABLE_CALL_ASSISTANT=true` (`.env.staging`)
- **Backend endpoint:** `POST /api/v1/call-requests`
- **Admin UI:** `https://staging.vejapro.lt/admin/calls`

---

## 1. Frontend Forma Testas (Landing Page)

### 1.1 Formos Atvaizdavimas
- [ ] Atidaryti `https://staging.vejapro.lt`
- [ ] Scroll į "Kontaktai" sekciją
- [ ] Patikrinti, kad forma matoma ir gerai atvaizduojama
- [ ] Patikrinti responsive dizainą (mobile, tablet, desktop)

### 1.2 Validacija
**Testas 1: Tuščia forma**
- [ ] Spausti "Siųsti Užklausą" be duomenų
- [ ] **Tikėtinas rezultatas:** Browser validacija reikalauja vardą ir telefoną

**Testas 2: Tik privalomi laukai**
- [ ] Įvesti vardą: "Jonas Jonaitis"
- [ ] Įvesti telefoną: "+37060012345"
- [ ] Spausti "Siųsti Užklausą"
- [ ] **Tikėtinas rezultatas:** Sėkmės pranešimas (žalias)

**Testas 3: Visi laukai užpildyti**
- [ ] Įvesti vardą: "Petras Petraitis"
- [ ] Įvesti telefoną: "+37061123456"
- [ ] Įvesti el. paštą: "petras@example.com"
- [ ] Įvesti laiką: "rytais 9-11 val."
- [ ] Įvesti pastabas: "Norėčiau įrengti 200 kv.m veją"
- [ ] Spausti "Siųsti Užklausą"
- [ ] **Tikėtinas rezultatas:** Sėkmės pranešimas, forma išvaloma

### 1.3 Klaidos Apdorojimas
**Testas 4: Neteisingas el. paštas**
- [ ] Įvesti vardą: "Test"
- [ ] Įvesti telefoną: "+37060000000"
- [ ] Įvesti el. paštą: "neteisingas-email"
- [ ] **Tikėtinas rezultatas:** Browser validacija sustabdo siuntimą

**Testas 5: Backend nepasiekiamas**
- [ ] Laikinai sustabdyti `vejapro-staging` service
- [ ] Bandyti siųsti formą
- [ ] **Tikėtinas rezultatas:** Klaidos pranešimas (raudonas)
- [ ] Paleisti service atgal

---

## 2. Backend API Testas

### 2.1 Tiesioginis API Testas
```bash
# SSH į VM
ssh administrator@10.10.50.178

# Testas 1: Sėkmingas užklausos sukūrimas
curl -X POST https://staging.vejapro.lt/api/v1/call-requests \
  -H "Content-Type: application/json" \
  -d '{
    "name": "API Test User",
    "phone": "+37060099999",
    "email": "apitest@example.com",
    "preferred_time": "popiet 14-16 val.",
    "notes": "API testas"
  }'

# Tikėtinas rezultatas: 201 Created + JSON su call_request ID
```

### 2.2 Validacijos Testas
```bash
# Testas 2: Trūksta privalomų laukų
curl -X POST https://staging.vejapro.lt/api/v1/call-requests \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test"
  }'

# Tikėtinas rezultatas: 422 Unprocessable Entity
```

### 2.3 Feature Flag Testas
```bash
# Testas 3: Išjungtas feature flag
# 1. Redaguoti .env.staging: ENABLE_CALL_ASSISTANT=false
# 2. Restart: sudo systemctl restart vejapro-staging
# 3. Bandyti siųsti užklausą
# Tikėtinas rezultatas: 404 Not Found

# 4. Įjungti atgal: ENABLE_CALL_ASSISTANT=true
# 5. Restart: sudo systemctl restart vejapro-staging
```

---

## 3. Admin UI Testas

### 3.1 Prieiga prie Admin Calls
- [ ] Atidaryti `https://staging.vejapro.lt/admin/calls`
- [ ] Įvesti admin bearer token (gauti iš `/api/v1/admin/token`)
- [ ] **Tikėtinas rezultatas:** Matomas skambučių sąrašas

### 3.2 Skambučių Sąrašas
- [ ] Patikrinti, kad matomi visi sukurti call requests
- [ ] Patikrinti, kad rodomas statusas (NEW, CONTACTED, SCHEDULED, COMPLETED, CANCELLED)
- [ ] Patikrinti, kad matoma data ir laikas

### 3.3 Skambučio Detalės
- [ ] Spausti "View" ant bet kurio skambučio
- [ ] **Tikėtinas rezultatas:** Modal su visais duomenimis:
  - Vardas
  - Telefonas
  - El. paštas (jei buvo įvestas)
  - Pageidaujamas laikas
  - Pastabos
  - Statusas
  - Sukūrimo data

### 3.4 Statuso Keitimas
- [ ] Atidaryti skambučio detales
- [ ] Pakeisti statusą iš "NEW" į "CONTACTED"
- [ ] Spausti "Save"
- [ ] **Tikėtinas rezultatas:** Sėkmės pranešimas, statusas atsinaujina

### 3.5 Pastabų Redagavimas
- [ ] Atidaryti skambučio detales
- [ ] Pridėti admin pastabą: "Susisiekta 2026-02-06, klientas patvirtino"
- [ ] Spausti "Save"
- [ ] **Tikėtinas rezultatas:** Pastaba išsaugoma

### 3.6 Filtravimas
- [ ] Filtruoti pagal statusą "NEW"
- [ ] **Tikėtinas rezultatas:** Rodomi tik nauji skambučiai
- [ ] Išvalyti filtrą
- [ ] **Tikėtinas rezultatas:** Rodomi visi skambučiai

---

## 4. Duomenų Bazės Testas

### 4.1 Call Requests Lentelė
```bash
# SSH į VM
ssh administrator@10.10.50.178

# Prisijungti prie staging DB
cd ~/VejaPRO
source .venv/bin/activate
export DATABASE_URL="<staging_db_url>"

# Patikrinti call_requests lentelę
python -c "
from sqlalchemy import create_engine, text
import os
engine = create_engine(os.getenv('DATABASE_URL'))
with engine.connect() as conn:
    result = conn.execute(text('SELECT id, name, phone, status, created_at FROM call_requests ORDER BY created_at DESC LIMIT 5'))
    for row in result:
        print(row)
"
```

**Tikėtinas rezultatas:**
- Matomi visi sukurti call requests
- `status` yra vienas iš: NEW, CONTACTED, SCHEDULED, COMPLETED, CANCELLED
- `created_at` ir `updated_at` laikai teisingi

### 4.2 Audit Log Testas
```bash
# Patikrinti audit_log įrašus
python -c "
from sqlalchemy import create_engine, text
import os
engine = create_engine(os.getenv('DATABASE_URL'))
with engine.connect() as conn:
    result = conn.execute(text(\"SELECT entity_type, entity_id, action, actor_type FROM audit_log WHERE entity_type='call_request' ORDER BY timestamp DESC LIMIT 5\"))
    for row in result:
        print(row)
"
```

**Tikėtinas rezultatas:**
- Kiekvienam call request sukūrimui yra `CALL_REQUEST_CREATED` įrašas
- Kiekvienam atnaujinimui yra `CALL_REQUEST_UPDATED` įrašas
- `actor_type` yra "PUBLIC" (formos) arba "ADMIN" (admin UI)

---

## 5. Integracija su Calendar

### 5.1 Appointment Sukūrimas iš Call Request
- [ ] Admin UI: atidaryti call request
- [ ] Spausti "Create Appointment" (jei toks mygtukas egzistuoja)
- [ ] Arba eiti į `/admin/calendar` ir sukurti appointment rankiniu būdu
- [ ] Susieti su call_request_id
- [ ] **Tikėtinas rezultatas:** Appointment sukurtas, call request statusas → SCHEDULED

---

## 6. Performance & Security Testas

### 6.1 Rate Limiting
```bash
# Siųsti 10 užklausų iš eilės
for i in {1..10}; do
  curl -X POST https://staging.vejapro.lt/api/v1/call-requests \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"Test$i\",\"phone\":\"+3706000000$i\"}"
  echo ""
done
```

**Tikėtinas rezultatas:**
- Pirmos užklausos sėkmingos (201)
- Jei viršijamas rate limit → 429 Too Many Requests

### 6.2 SQL Injection Testas
```bash
# Bandyti SQL injection
curl -X POST https://staging.vejapro.lt/api/v1/call-requests \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test'; DROP TABLE call_requests;--",
    "phone": "+37060000000"
  }'
```

**Tikėtinas rezultatas:**
- Užklausa sukuriama normaliai (SQLAlchemy apsaugo nuo injection)
- Lentelė neištrinima

### 6.3 XSS Testas
- [ ] Formos lauke įvesti: `<script>alert('XSS')</script>`
- [ ] Pateikti formą
- [ ] Atidaryti Admin UI ir peržiūrėti įrašą
- [ ] **Tikėtinas rezultatas:** Script neįvykdomas (HTML escaped)

---

## 7. Smoke Test (Pilnas Srautas)

### End-to-End Scenarijus
1. **Klientas pateikia užklausą:**
   - [ ] Atidaryti `https://staging.vejapro.lt`
   - [ ] Užpildyti formą
   - [ ] Gauti sėkmės pranešimą

2. **Admin gauna užklausą:**
   - [ ] Atidaryti `https://staging.vejapro.lt/admin/calls`
   - [ ] Matyti naują užklausą su statusu "NEW"

3. **Admin susisiekia:**
   - [ ] Pakeisti statusą į "CONTACTED"
   - [ ] Pridėti pastabą: "Susisiekta telefonu, klientas patvirtino"

4. **Admin sukuria susitikimą:**
   - [ ] Eiti į `/admin/calendar`
   - [ ] Sukurti appointment su call_request_id
   - [ ] Call request statusas → "SCHEDULED"

5. **Admin užbaigia:**
   - [ ] Pakeisti call request statusą į "COMPLETED"
   - [ ] Patikrinti audit log

---

## 8. Rollback Planas

Jei Call Assistant neveikia staging:
```bash
# 1. Išjungti feature flag
ssh administrator@10.10.50.178
cd ~/VejaPRO
nano backend/.env.staging
# Nustatyti: ENABLE_CALL_ASSISTANT=false

# 2. Restart service
sudo systemctl restart vejapro-staging

# 3. Patikrinti
curl https://staging.vejapro.lt/health
```

---

## 9. Production Deployment Checklist

Prieš įjungiant production:
- [ ] Visi staging testai praėjo sėkmingai
- [ ] Audit log veikia teisingai
- [ ] Rate limiting veikia
- [ ] XSS/SQL injection apsauga veikia
- [ ] Admin UI veikia be klaidų
- [ ] Landing page forma veikia mobile ir desktop
- [ ] `.env.prod` atnaujintas su `ENABLE_CALL_ASSISTANT=true`
- [ ] Production deploy atliktas pagal `SYSTEM_CONTEXT.md`
- [ ] UptimeRobot monitoringas veikia

---

## 10. Metrika ir Monitoringas

### Stebėti:
- Call requests per dieną
- Vidutinis atsakymo laikas (NEW → CONTACTED)
- Conversion rate (NEW → SCHEDULED → COMPLETED)
- Bounce rate landing page formoje

### Logai:
```bash
# Backend logai
journalctl -u vejapro-staging -f | grep call_request

# Nginx logai
sudo tail -f /var/log/nginx/access.log | grep "/api/v1/call-requests"
```

---

## Kontaktai
Jei kyla klausimų ar problemų, žiūrėti:
- `SYSTEM_CONTEXT.md` - deployment ir troubleshooting
- `PROJECT_CONTEXT.md` - projekto kontekstas
- `backend/README.md` - API dokumentacija
