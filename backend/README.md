# 📚 VejaPRO Dokumentacija

Sveiki atvykę į VejaPRO dokumentacijos centrą!

## 📖 Turinys

### 🏆 Pagrindiniai Dokumentai

1. **[VEJAPRO_KONSTITUCIJA_V1.3.md](./VEJAPRO_KONSTITUCIJA_V1.3.md)** - Sistemos pagrindinis dokumentas (bazė)
   - Sistemos architektūra
   - Verslo logikos taisyklės
   - API specifikacija
   - Statusų valdymas
   - AI integracijos principai

2. **[VEJAPRO_KONSTITUCIJA_V1.4.md](./VEJAPRO_KONSTITUCIJA_V1.4.md)** - Payments-first korekcija (manual default, Stripe optional)

3. **[VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md](./VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md)** - 🔒 Techninė spec programuotojui **V.1.52** (bazė)
   - DB Schema (copy-paste ready)
   - Statusų perėjimo mašina (Python kodu)
   - Kritiniai API endpoints su prioritetais
   - AI integracijos stack (LangChain + Groq)
   - Dokumentų generavimas
   - Sprint #1 užduotys
   - Saugikliai ir validacijos
   - **🆕 Marketingo & Web Modulis** (Galerija, Before/After slider, Auto-location)

4. **[VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.1.md](./VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.1.md)** - Patch (payments-first)

## 🎯 Greita Navigacija

### Pagal Temą

- **Architektūra** → [Konstitucija § 1](./VEJAPRO_KONSTITUCIJA_V1.3.md#1-sistemos-stuburas-core-domain)
- **Statusų Ciklas** → [Konstitucija § 2](./VEJAPRO_KONSTITUCIJA_V1.3.md#2-projektų-statusų-ciklas-forward-only)
- **API Endpoints** → [Konstitucija § 5](./VEJAPRO_KONSTITUCIJA_V1.3.md#5-techninė-užduotis-api-endpoints)
- **Sertifikavimas** → [Konstitucija § 6](./VEJAPRO_KONSTITUCIJA_V1.3.md#6-eksperto-sertifikavimo-checklistas)
- **DB Schema** → [Tech Docs § 2](./VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md#2-duomenų-bazės-schema)
- **State Machine** → [Tech Docs § 3](./VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md#3-statusų-perėjimo-mašina)
- **Sprint #1** → [Tech Docs § 7](./VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md#7-pirmos-savaitės-sprint-1-užduotys)
- **🆕 Marketingo Modulis** → [Tech Docs § 9](./VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md#9-marketingo--web-modulis)

### Pagal Rolę

#### 👨‍💻 Backend Developer
- [Sistemos Stuburas](./VEJAPRO_KONSTITUCIJA_V1.3.md#1-sistemos-stuburas-core-domain)
- [API Endpoints](./VEJAPRO_KONSTITUCIJA_V1.3.md#5-techninė-užduotis-api-endpoints)
- [Audit Log](./VEJAPRO_KONSTITUCIJA_V1.3.md#85-audit-log-privalomas)
- 🔥 **[DB Schema (SQL)](./VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md#2-duomenų-bazės-schema)**
- 🔥 **[State Machine (Python)](./VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md#3-statusų-perėjimo-mašina)**
- 🔥 **[Sprint #1 Tasks](./VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md#7-pirmos-savaitės-sprint-1-užduotys)**

#### 🎨 Frontend Developer
- [Klientų Architektūra](./VEJAPRO_KONSTITUCIJA_V1.3.md#12-klientų-architektūra)
- [Statusų Diagrama](./VEJAPRO_KONSTITUCIJA_V1.3.md#21-statusų-diagrama)
- [UX Principai](./VEJAPRO_KONSTITUCIJA_V1.3.md#83-klientas-negaišta-laiko)

#### 🤖 AI/ML Engineer
- [AI Diegimo Logika](./VEJAPRO_KONSTITUCIJA_V1.3.md#4-ai-diegimo-ir-teisinė-logika)
- [Feature Flags](./VEJAPRO_KONSTITUCIJA_V1.3.md#72-feature-flags)
- [AI Principai](./VEJAPRO_KONSTITUCIJA_V1.3.md#81-ai-yra-pagalbininkas-ne-sprendėjas)
- 🔥 **[AI Stack (LangChain + Groq)](./VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md#5-ai-integracijos-taisyklės)**
- 🔥 **[AI Apribojimai](./VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md#52-ai-apribojimai)**

#### 📊 Product Owner
- [Etapiškumas](./VEJAPRO_KONSTITUCIJA_V1.3.md#3-etapiškumas-ir-exit-criteria)
- [Verslo Principai](./VEJAPRO_KONSTITUCIJA_V1.3.md#8-principai-kurių-niekada-nekeičiame)

#### 🌱 Agronomas/Ekspertas
- [Sertifikavimo Checklist](./VEJAPRO_KONSTITUCIJA_V1.3.md#6-eksperto-sertifikavimo-checklistas)
- [Veto Teisė](./VEJAPRO_KONSTITUCIJA_V1.3.md#82-ekspertas-turi-veto-teisę)

## 🚀 Greitas Startas

### Naujiems Komandos Nariams

1. **Pirmiausia skaityk:** [Konstitucija](./VEJAPRO_KONSTITUCIJA_V1.3.md)
2. **Supažindink su:** [8 Principais](./VEJAPRO_KONSTITUCIJA_V1.3.md#8-principai-kurių-niekada-nekeičiame)
3. **Išmok:** [Statusų Ciklą](./VEJAPRO_KONSTITUCIJA_V1.3.md#2-projektų-statusų-ciklas-forward-only)

### Programuotojui - Greitas Startas

1. **Skaityk:** [Techninė Dokumentacija V.1.5](./VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md)
2. **Kopijuok:** [DB Schema](./VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md#2-duomenų-bazės-schema)
3. **Implementuok:** [State Machine](./VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md#3-statusų-perėjimo-mašina)
4. **Pradėk:** [Sprint #1](./VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md#7-pirmos-savaitės-sprint-1-užduotys)

## Testu Paleidimas

1. Unit ir API testai (be serverio)
```bash
cd ~/VejaPRO
source .venv/bin/activate
PYTHONPATH=backend python -m pytest backend/tests -q
```

2. API testai su paleistu serveriu
```bash
cd ~/VejaPRO
source .venv/bin/activate
export DATABASE_URL="sqlite:////tmp/veja_api_test.db"
export SUPABASE_JWT_SECRET="testsecret_testsecret_testsecret_test"
export ALLOW_INSECURE_WEBHOOKS=true
export ENABLE_MARKETING_MODULE=true
export PYTHONPATH=backend
python - <<'PY'
from app.core.dependencies import engine
from app.models.project import Base
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
PY
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

3. API testai (kitame terminale)
```bash
cd ~/VejaPRO
source .venv/bin/activate
export BASE_URL="http://127.0.0.1:8001"
export SUPABASE_JWT_SECRET="testsecret_testsecret_testsecret_test"
export TEST_AUTH_ROLE="ADMIN"
PYTHONPATH=backend python -m pytest backend/tests/api -q
```

## Admin UI

- `/admin` (overview)
- `/admin/projects`
- `/admin/calls`
- `/admin/calendar`
- `/admin/audit`
- `/admin/margins`

Token is stored in the browser under `vejapro_admin_token`.
Projects UI actions include details, status transition, seed certification photos, and certify (admin-only).
Calls UI lists incoming call requests and allows admin status updates.
Calendar UI lists appointments and allows scheduling/updates.

### Feature Flags (Server)

- `ENABLE_CALL_ASSISTANT` (default false) — enables public call request intake + admin call inbox.
- `ENABLE_CALENDAR` (default false) — enables admin appointment scheduling endpoints.

## Diegimo ir Testu Zurnalas

- 2026-02-04: [Deployment Notes 2026-02-04](./DEPLOYMENT_NOTES_2026-02-04.md)
- 2026-02-05: [Go-Live Plan](./GO_LIVE_PLAN.md)
- 2026-02-05: [Data Security Plan](./DATA_SECURITY_PLAN.md)
- 2026-02-07: [Schedule Engine V1 Spec](./SCHEDULE_ENGINE_V1_SPEC.md)

### Prieš Pradedant Kodą

- [ ] Perskaičiau Konstituciją
- [ ] Perskaičiau Techninę Dokumentaciją
- [ ] Suprantu statusų ciklą
- [ ] Žinau API endpoints
- [ ] Suprantu AI ribas
- [ ] Žinau audit log reikalavimus
- [ ] Suprantu feature flags sistemą

## 📋 Dokumentų Struktūra

```
backend/
├── README.md                                    # Šis failas - navigacija
├── VEJAPRO_KONSTITUCIJA_V1.3.md                # Verslo logika ir principai
├── VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md      # 🔒 Tech spec programuotojui
└── (būsimi dokumentai)
```

## 🔄 Atnaujinimai

Dokumentacija atnaujinama kas mėnesį arba po svarbių sistemos pakeitimų.

**Paskutinis atnaujinimas:** 2026-02-03  
**Kita peržiūra:** 2026-03-01

## 📞 Kontaktai

Klausimų atveju kreipkitės:

- **Techniniai klausimai:** tech@vejapro.lt
- **Verslo logika:** product@vejapro.lt
- **Sertifikavimas:** expert@vejapro.lt

## ⚠️ Svarbu

> **KRITINĖ TAISYKLĖ:** Prieš darydamas bet kokius pakeitimus sistemoje, **VISADA** patikrink Konstituciją.
> 
> Jei kažkas prieštarauja Konstitucijai - keičiame kodą, ne Konstituciją (išskyrus oficialias revizijas).

---

© 2026 VejaPRO. Visos teisės saugomos.

### Feature Flags (Schedule Engine)
- `ENABLE_SCHEDULE_ENGINE` (default false) - ijungia schedule engine endpointus.
- `HOLD_DURATION_MINUTES` (default 3) - Voice/Chat hold trukme minutemis.
- `SCHEDULE_PREVIEW_TTL_MINUTES` (default 15) - preview galiojimo trukme.
- `SCHEDULE_USE_SERVER_PREVIEW` (default true) - server-side preview rezimas.
- `SCHEDULE_DAY_NAMESPACE_UUID` - UUIDv5 namespace `schedule_day` audit entity_id generavimui.

### Schedule Engine API (Phase 0)
- `POST /api/v1/admin/schedule/reschedule/preview`
- `POST /api/v1/admin/schedule/reschedule/confirm`

Detalus aprasas: `SCHEDULE_ENGINE_V1_SPEC.md`.
Likusiu darbu sarasas: `SCHEDULE_ENGINE_BACKLOG.md`.

### Schedule Engine API (Phase 2 - Voice/Chat Hold)
- `POST /api/v1/admin/schedule/holds`
- `POST /api/v1/admin/schedule/holds/confirm`
- `POST /api/v1/admin/schedule/holds/cancel`
- `POST /api/v1/admin/schedule/holds/expire`

### Schedule Engine API (Phase 3 - Daily Batch Approve)
- `POST /api/v1/admin/schedule/daily-approve`
