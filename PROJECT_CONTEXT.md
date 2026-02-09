# PROJECT_CONTEXT

Trumpas projekto kontekstas ir kur rasti pilna specifikacija.

## Projekto esme
VejaPRO yra projektu valdymo ir sertifikavimo sistema. Pagrindinis srautas:
- Kliento projektas kuriamas -> vyksta apmokejimas -> planavimas -> eksperto patikra -> sertifikavimas -> aktyvus projektas.
- Visi statusai ir leidziami perejimai apibrezti dokumentacijoje.

## Pagrindiniai moduliai
- Projektų API (sukūrimas, peržiūra, statusų perėjimai).
- Audit log (privalomas visoms kritinėms veiksmams).
- Mokėjimai (Stripe + grynieji) + webhooks / rankinis cash patvirtinimas (payments-first doktrina).
- SMS (Twilio) ir Email patvirtinimai (`client_confirmations` lentelė su `channel` stulpeliu: sms, email, whatsapp).
- Evidence upload + sertifikavimo workflow + nuotraukų optimizavimas (Pillow: thumbnail WebP, medium WebP).
- Marketing/Gallery modulis (priklausomai nuo feature flag) su blur-up placeholder ir responsive images.
- Admin API ir Admin UI (projektai, auditas, maržos, skambučiai, kalendorius).
- Call Assistant — skambučių užklausų priėmimas per landing page formą.
- Email Intake (Unified Client Card) — anketa → pasiūlymo siuntimas su .ics → accept/reject per email nuorodą.
- Schedule Engine — RESCHEDULE preview/confirm, HOLD rezervacijos (Voice/Chat), daily batch approve.
- Voice webhook (Twilio) — automatinis laiko pasiūlymas su HELD + patvirtinimas/atšaukimas.
- Chat webhook + web chat widget (`/chat`) — pokalbio HELD pasiūlymo srautas.
- Notification outbox — asinchroninė SMS/email/WhatsApp pranešimų eilė su idempotencija ir retry.
- Hold expiry worker — periodinis HELD rezervacijų valymas.
- Finance modulis — išlaidų/pajamų knyga (ledger), dokumentų upload su SHA-256 dedup, AI ekstrakcija, vendor taisyklės, Quick Payment.
- Klientų portalas (`/client`) — projekto eigos peržiūra, rinkodaros sutikimas.
- Rangovo portalas (`/contractor`) — priskirtų projektų valdymas.
- Eksperto portalas (`/expert`) — sertifikavimo workflow, checklist, evidence.
- Galerija (`/gallery`) — viešoji projektų galerija su before/after nuotraukomis.

## Dokumentacija (pilna)
- `backend/VEJAPRO_KONSTITUCIJA_V1.3.md` — verslo logikos specifikacija
- `backend/VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md` — techninė dokumentacija
- `backend/README.md` — navigacija ir testų paleidimas
- `backend/CONTRACTOR_EXPERT_PORTALS.md` — rangovo/eksperto portalų dokumentacija
- `backend/GALLERY_DOCUMENTATION.md` — galerijos modulio dokumentacija
- `backend/CALL_ASSISTANT_TEST_PLAN.md` — skambučių užklausų testavimo planas
- `backend/SCHEDULE_ENGINE_V1_SPEC.md` - planavimo masinos logika (vienas operatorius, chat + call)
- `SYSTEM_CONTEXT.md` — infrastruktūros ir deploy dokumentacija
- `backend/PROGRESS_LOCK.md` — darbų žurnalas (DONE eilučių nekeisti)

## Naujausia darbiniu pakeitimu ataskaita
- `WORKLOG_2026-02-07_UI_SECURITY.md`

## Feature flags
- `ENABLE_MARKETING_MODULE` — galerija ir marketingo funkcijos
- `ENABLE_CALL_ASSISTANT` — skambučių užklausų modulis
- `ENABLE_CALENDAR` — kalendoriaus/susitikimų modulis
- `ENABLE_SCHEDULE_ENGINE` — planavimo variklis (RESCHEDULE, HOLD, daily-approve)
- `ENABLE_MANUAL_PAYMENTS` — grynųjų/banko mokėjimai (default: true)
- `ENABLE_STRIPE` — Stripe mokėjimai (default: false)
- `ENABLE_TWILIO` — SMS per Twilio
- `ENABLE_NOTIFICATION_OUTBOX` — asinchroninių pranešimų eilė
- `ENABLE_VISION_AI` — AI nuotraukų analizė (Groq/Claude)
- `ENABLE_RECURRING_JOBS` — background worker'iai (hold expiry, outbox)
- `ENABLE_FINANCE_LEDGER` — finansų knyga (ledger CRUD, suvestinės, reversal)
- `ENABLE_FINANCE_AI_INGEST` — dokumentų upload + AI ekstrakcija
- `ENABLE_FINANCE_AUTO_RULES` — automatinis vendor taisyklių pritaikymas
- `ENABLE_EMAIL_INTAKE` — email intake (Unified Client Card) modulis (default: false)
- `EMAIL_HOLD_DURATION_MINUTES` — email pasiūlymo HELD trukmė (default: 30)
- `EMAIL_OFFER_MAX_ATTEMPTS` — max pasiūlymo bandymų skaičius (default: 5)
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_USE_TLS` — SMTP konfigūracija email siuntimui
- `ENABLE_WHATSAPP_PING` — WhatsApp ping pranešimai (stub, default: false)
- `ALLOW_INSECURE_WEBHOOKS` (testams — prod turi būti `false`)

## Lokalizacija (i18n)
- Visa web sąsaja yra **lietuvių kalba** — pilnai sulietuvinti visi **11 HTML failų** (`lang="lt"`).
- ~**70 backend API klaidų pranešimų** išversti į lietuvių kalbą (`projects.py`, `assistant.py`, `schedule.py`, `transition_service.py`).
- Frontend JS pranešimai (loading, klaidos, būsenos, patvirtinimai) — lietuviškai (`projects.html`, `admin.html`, `calendar.html`, `contractor.html`, `audit.html`, `margins.html` ir kt.).
- Naudojami teisingi diakritikai: ą, č, ę, ė, į, š, ų, ū, ž.
- Datų formatavimas: `flatpickr` su LT locale, 24h formatas, pirmadienis savaitės pradžia.

## Testai (santrauka)
Unit/API testu instrukcijos yra `backend/README.md`.
Greitas paleidimas (VM):
```
cd ~/VejaPRO
source .venv/bin/activate
PYTHONPATH=backend python -m pytest backend/tests -q
```

## Staging testu scenarijus (realus DATABASE_URL)
Tik staging DB. Nenaudoti production DB testams.

0) `.env.staging` failas nera repo (neateina su `git pull`).

1) Nustatyk staging URL:
```
export DATABASE_URL_STAGING="postgresql://USER:PASS@HOST:5432/DB?sslmode=require"
```

2) Priskirk ji testui (laikinai):
```
export DATABASE_URL="$DATABASE_URL_STAGING"
export PYTHONPATH=backend
```

3) Migracijos i staging:
```
alembic -c backend/alembic.ini upgrade head
```

4) Jei naudoji staging servisa:
```
sudo systemctl restart vejapro-staging
```

5) Paleisk API lokaliai (staging DB):
```
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

6) API testai:
```
BASE_URL="http://127.0.0.1:8001" PYTHONPATH=backend python -m pytest backend/tests/api -q
```

7) Smoke flow (rankinis):
- Create project
- Stripe DEPOSIT -> status PAID
- Schedule -> PENDING_EXPERT
- Seed evidence (3 photos)
- Certify -> CERTIFIED
- FINAL payment -> SMS -> ACTIVE

Pastaba: testams gali prireikti `ALLOW_INSECURE_WEBHOOKS=true` (tik staging).

## Portalų sąrašas

| Kelias | Failas | Paskirtis | Prieiga | Mobilus |
|--------|--------|-----------|---------|--------|
| `/` | `landing.html` | Viešas pradinis puslapis, užklausos forma | Vieša | ✓ |
| `/gallery` | `gallery.html` | Viešoji projektų galerija | Vieša | ✓ |
| `/chat` | `chat.html` | Web chat widget (testavimo UI) | Vieša | ✓ |
| `/client` | `client.html` | Klientų portalas (projekto eiga) | JWT | ✓ |
| `/contractor` | `contractor.html` | Rangovo portalas (priskirti projektai) | JWT | ✓ |
| `/expert` | `expert.html` | Eksperto portalas (sertifikavimas) | JWT | ✓ |
| `/admin` | `admin.html` | Administravimo apžvalga | JWT + IP | ✓ |
| `/admin/projects` | `projects.html` | Projektų valdymas | JWT + IP | ✓ |
| `/admin/calls` | `calls.html` | Skambučių užklausos | JWT + IP | ✓ |
| `/admin/calendar` | `calendar.html` | Kalendorius + Schedule Engine | JWT + IP | ✓ |
| `/admin/audit` | `audit.html` | Audito žurnalas | JWT + IP | ✓ |
| `/admin/margins` | `margins.html` | Maržų taisyklės | JWT + IP | ✓ |
| `/admin/finance` | `finance.html` | Finansų knyga (ledger, dokumentai, taisyklės) | JWT + IP | ✓ |
| `/admin/ai` | `ai-monitor.html` | AI monitoring dashboard | JWT + IP | ✓ |

## Pastabos
- `backend/PROGRESS_LOCK.md` naudojamas kaip darbų žurnalas. DONE eilučių nekeisti.
- Jei reikia naujos funkcijos ar pakeitimo, pirmiausia sutikrinti su Konstitucija.
- Visa UI sąsaja yra lietuvių kalba — keičiant tekstą naudoti teisingus diacritikus.

## Schedule Engine (2026-02-08 statusas)
- **Phase 0** (RESCHEDULE preview/confirm): DONE
- **Phase 2** (HELD rezervacijos + conversation_locks): DONE
- **Phase 3** (Daily batch approve): DONE
- **Voice webhook** (Twilio): DONE
- **Chat webhook** + web chat widget: DONE
- **Hold expiry worker**: DONE
- **Notification outbox** (SMS + Email + WhatsApp): DONE
- Technine specifikacija: `backend/SCHEDULE_ENGINE_V1_SPEC.md`
- Likę darbai: `backend/SCHEDULE_ENGINE_BACKLOG.md`

## V2.2 Unified Client Card (2026-02-09 statusas)

- **Email intake flow**: DONE — anketa, pasiūlymas, .ics, accept/reject per public link.
- **Multi-channel notification outbox**: DONE — email (SMTP + .ics), WhatsApp ping (stub), SMS (legacy).
- **client_confirmations**: DONE — pervadinta iš `sms_confirmations`, pridėtas `channel` stulpelis.
- **SYSTEM_EMAIL aktorius**: DONE — CERTIFIED→ACTIVE per email patvirtinimą.
- **Admin Calls UI**: DONE — intake anketa, pasiūlymo valdymas, evidence grid.
- **DB migracija**: `20260209_000015_unified_client_card_v22.py`.
- **Alembic HEAD**: `20260209_000015`.

## Dabartinis kursas (2026-02-09)

### CI stabilizacija — PASS
- `ruff check` PASS, `ruff format --check` PASS (96 failai), `pytest` PASS.
- Testai CI veikia in-process (be uvicorn), bet galima opt-in per `USE_LIVE_SERVER=true` + `BASE_URL=...`.
- SQLite / Postgres suderinamumas: `SELECT ... FOR UPDATE` vengimas SQLite aplinkoje (jau sutvarkytas).
- Settings cache reset: autouse fixture testuose (jau sutvarkytas).

### Liko padaryti (prioritetu tvarka)
1. **Stripe/Twilio LIVE raktu perjungimas** — siuo metu TEST rezimas.
2. **Galutinis smoke test su LIVE raktais** — pilnas srautas DRAFT->ACTIVE.
3. **Email intake smoke test** — pilnas srautas: call request → intake anketa → prepare → send offer → accept per public link.
4. **SMTP konfigūracija produkcijoje** — `.env.prod` papildyti SMTP_HOST, SMTP_USER, SMTP_PASSWORD ir tt.
5. **Alembic migracija produkcijoje** — `alembic upgrade head` (20260209_000015).
6. **Schedule Engine backlog** — zr. `SCHEDULE_ENGINE_BACKLOG.md`:
   - RESCHEDULE scope pasirinkimas (DAY/WEEK) Admin UI.
7. **Neprivalomi patobulinimai:**
   - Vision AI integracija (feature flag `ENABLE_VISION_AI`).
   - WhatsApp API integracija (vietoj stub).
   - Redis cache galerijos/projektu API.
   - CDN nuotraukoms.
