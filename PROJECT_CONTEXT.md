# PROJECT_CONTEXT

Trumpas projekto kontekstas ir kur rasti pilna specifikacija.

## Projekto esme
VejaPRO yra projektu valdymo ir sertifikavimo sistema. Pagrindinis srautas:
- Kliento projektas kuriamas -> vyksta apmokejimas -> planavimas -> eksperto patikra -> sertifikavimas -> aktyvus projektas.
- Visi statusai ir leidziami perejimai apibrezti dokumentacijoje.

## Pagrindiniai moduliai
- Projektu API (sukurimas, perziura, statusu perejimai).
- Audit log (privalomas visoms kritinems veiksmams).
- Mokejimai (Stripe) + webhooks.
- SMS (Twilio) patvirtinimai.
- Evidence upload + sertifikavimo workflow.
- Marketing/Gallery modulis (priklausomai nuo feature flag).
- Admin API ir Admin UI (projekty, audit, margins, calls, calendar).

## Dokumentacija (pilna)
- `backend/VEJAPRO_KONSTITUCIJA_V1.3.md`
- `backend/VEJAPRO_TECHNINE_DOKUMENTACIJA_V1.5.md`
- Navigacija ir testu paleidimas: `backend/README.md`

## Feature flags
- `ENABLE_MARKETING_MODULE`
- `ENABLE_CALL_ASSISTANT`
- `ENABLE_CALENDAR`
- `ALLOW_INSECURE_WEBHOOKS` (testams)

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

4) Paleisk API lokaliai (staging DB):
```
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

5) API testai:
```
BASE_URL="http://127.0.0.1:8001" PYTHONPATH=backend python -m pytest backend/tests/api -q
```

6) Smoke flow (rankinis):
- Create project
- Stripe DEPOSIT -> status PAID
- Schedule -> PENDING_EXPERT
- Seed evidence (3 photos)
- Certify -> CERTIFIED
- FINAL payment -> SMS -> ACTIVE

Pastaba: testams gali prireikti `ALLOW_INSECURE_WEBHOOKS=true` (tik staging).

## Pastabos
- `backend/PROGRESS_LOCK.md` naudojamas kaip darbu zurnalas. DONE eiluciu nekeisti.
- Jei reikia naujos funkcijos ar pakeitimo, pirmiausia sutikrinti su Konstitucija.
