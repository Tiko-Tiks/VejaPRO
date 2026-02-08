# PROJECT_CONTEXT

Trumpas projekto kontekstas ir kur rasti pilna specifikacija.

## Projekto esme
VejaPRO yra projektu valdymo ir sertifikavimo sistema. Pagrindinis srautas:
- Kliento projektas kuriamas -> vyksta apmokejimas -> planavimas -> eksperto patikra -> sertifikavimas -> aktyvus projektas.
- Visi statusai ir leidziami perejimai apibrezti dokumentacijoje.

## Pagrindiniai moduliai
- Projektų API (sukūrimas, peržiūra, statusų perėjimai).
- Audit log (privalomas visoms kritinėms veiksmams).
- Mokėjimai (Stripe + grynieji) + webhooks / rankinis cash patvirtinimas.
- SMS (Twilio) patvirtinimai.
- Evidence upload + sertifikavimo workflow.
- Marketing/Gallery modulis (priklausomai nuo feature flag).
- Admin API ir Admin UI (projektai, auditas, maržos, skambučiai, kalendorius).
- Call Assistant — skambučių užklausų priėmimas per landing page formą.
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
| `/client` | `client.html` | Klientų portalas (projekto eiga) | JWT | ✓ |
| `/contractor` | `contractor.html` | Rangovo portalas (priskirti projektai) | JWT | ✓ |
| `/expert` | `expert.html` | Eksperto portalas (sertifikavimas) | JWT | ✓ |
| `/admin` | `admin.html` | Administravimo apžvalga | JWT + IP | ✓ |
| `/admin/projects` | `projects.html` | Projektų valdymas | JWT + IP | ✓ |
| `/admin/calls` | `calls.html` | Skambučių užklausos | JWT + IP | ✓ |
| `/admin/calendar` | `calendar.html` | Kalendorius | JWT + IP | ✓ |
| `/admin/audit` | `audit.html` | Audito žurnalas | JWT + IP | ✓ |
| `/admin/margins` | `margins.html` | Maržų taisyklės | JWT + IP | ✓ |

## Pastabos
- `backend/PROGRESS_LOCK.md` naudojamas kaip darbų žurnalas. DONE eilučių nekeisti.
- Jei reikia naujos funkcijos ar pakeitimo, pirmiausia sutikrinti su Konstitucija.
- Visa UI sąsaja yra lietuvių kalba — keičiant tekstą naudoti teisingus diacritikus.

## Schedule Engine Snapshot (2026-02-07)
- Pradeta `Schedule Engine` backend implementacija su feature flag `ENABLE_SCHEDULE_ENGINE`.
- Nauji API endpointai:
  - `POST /api/v1/admin/schedule/reschedule/preview`
  - `POST /api/v1/admin/schedule/reschedule/confirm`
- Nauji env kintamieji:
  - `HOLD_DURATION_MINUTES`
  - `SCHEDULE_PREVIEW_TTL_MINUTES`
  - `SCHEDULE_USE_SERVER_PREVIEW`
  - `SCHEDULE_DAY_NAMESPACE_UUID`
- Technine specifikacija ir statusas: `backend/SCHEDULE_ENGINE_V1_SPEC.md`.

## Dabartinis kursas (2026-02-08)
- Stabilizacija / CI disciplina: palaikyti `main` Å¾aliÄ… (ruff + pytest).
- Testai CI veikia in-process (be uvicorn), bet galima opt-in per `USE_LIVE_SERVER=true` + `BASE_URL=...`.
- Toliau: jei CI krenta dÄ—l SQLite konkurencingumo (lock'ai), pirmas taisymas yra DB engine SQLite konfig (timeout + thread-safety) `backend/app/core/dependencies.py`.
- Toliau: `Schedule Engine` endpointuose vengti `SELECT ... FOR UPDATE` SQLite aplinkoje (Postgres lieka su row locks), kad CI/testai nepriklausyt? nuo DB dialekto.
- Stabilizacija: testuose priverstinai resetinamas `get_settings` cache (autouse fixture), kad audience/secret monkeypatch i? `test_auth_jwt_audience` nelau?yt? kit? test?.
