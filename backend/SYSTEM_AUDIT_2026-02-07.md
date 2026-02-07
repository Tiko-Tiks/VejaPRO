# PILNAS SISTEMOS AUDITAS — ATASKAITA

Data: 2026-02-07

Verdiktas: sistema veikia stabiliai (CI "žalias", testai praeina), tačiau yra keli aiškūs "schema higienos" neatitikimai tarp SQLAlchemy modelių ir Alembic migracijų. Stuburas nepažeistas, bet šiuos drift'us verta sutvarkyti, kad DB taisyklės būtų kanoninės ir neatsirastų paslėptų IntegrityError ar neteisingų duomenų.

## Kas patikrinta (high-level)

- CI disciplina: `lint` blokuoja (nėra `continue-on-error`), testai turi `needs: lint`.
- Schedule Engine: `no-overlap` semantika suvienodinta tarp SQLite (app-guard) ir Postgres (DB constraint).
- Admin UI: `/admin/calendar` turi "Hold įrankiai" ir "RESCHEDULE" testavimo blokus.

## SVEIKA (viskas gerai)

- Nėra sulaužytų importų, nėra akivaizdžių nuorodų į ištrintus modulius (CI lint praeina).
- Backend testų paketas veikia (CI `pytest` praeina).
- Schedule Engine overlap taisyklė atitinka spec: overlap blokuoja `HELD` + `CONFIRMED` visada (be expiry išimčių).

## PROBLEMOS (reikia taisyti)

### P1 (kritinė) — `chk_appointment_time` nėra DB migracijose

**Modelis:** `backend/app/models/project.py` turi `CheckConstraint("ends_at > starts_at", name="chk_appointment_time")` (Appointment `__table_args__`).

**Migracijos:**
- Pradinis `appointments` table sukūrimas `backend/app/migrations/versions/20260205_000003_add_call_calendar_tables.py` neturi jokio `CheckConstraint` `ends_at > starts_at`.
- Schedule Engine Phase 0 migracija `backend/app/migrations/versions/20260207_000007_schedule_engine_phase0.py` prideda `chk_appt_link` ir `chk_hold_only_when_held`, bet neprideda `chk_appointment_time`.

**Poveikis:** Postgres DB gali priimti `appointments` su `ends_at <= starts_at` (modelis/testai to "nemato", nes ORM turi constraint'ą, bet DB kanoniškai jo neturi).

**Taisymas:** nauja Alembic migracija, kuri prideda `chk_appointment_time` į `appointments` (ir downgrade nuima).

### P2 (vidutinė) — `Appointment.lock_level` tipo neatitikimas (modelis vs migracija)

**Modelis:** `backend/app/models/project.py` turi `lock_level = Column(Integer, ...)`.

**Migracija:** `backend/app/migrations/versions/20260207_000007_schedule_engine_phase0.py` prideda `lock_level` kaip `SmallInteger`.

**Poveikis:** autogenerate drift + potencialus netikslumas. Semantiškai `lock_level` yra 0/1/2, todėl `SmallInteger` yra teisingas.

**Taisymas:** suvienodinti tipą (rekomenduojama: pakeisti modelį į `SmallInteger`, o DB palikti kaip `SmallInteger`).

### P3 (vidutinė) — `created_at` / `timestamp` NOT NULL drift

**Modeliuose:** `nullable=False` (pvz. `backend/app/models/project.py`).

**Migracijoje:** `backend/app/migrations/versions/20260203_000001_init_core_schema.py` dalyje lentelių `created_at` / `timestamp` turi `server_default=now()`, bet `nullable=False` nenurodyta.

Pastebėta:
- `users.created_at` (nullable nenurodyta)
- `margins.created_at` (nullable nenurodyta)
- `payments.created_at` (nullable nenurodyta)
- `sms_confirmations.created_at` (nullable nenurodyta)
- `audit_logs.timestamp` (nullable nenurodyta)

**Poveikis:** `server_default` maskuoja daugumą atvejų, bet tiesioginis `NULL INSERT` (ar neteisingas importas) gali praeiti DB lygyje.

**Taisymas:** migracija, kuri:
- backfill: `UPDATE ... SET created_at = now() WHERE created_at IS NULL` (ir analogiškai `timestamp`),
- `ALTER TABLE ... ALTER COLUMN ... SET NOT NULL`.

### P4 (žema) — atvirkštinis nullable drift (DB griežčiau nei ORM)

**DB (migracijoje):** `nullable=False`:
- `projects.has_robot`, `projects.is_certified` (`backend/app/migrations/versions/20260203_000001_init_core_schema.py`)
- `evidences.show_on_web`, `evidences.is_featured` (`backend/app/migrations/versions/20260203_000001_init_core_schema.py`)

**Modeliuose:** `nullable` nenurodyta (pagal nutylėjimą ORM leidžia `NULL`).

**Poveikis:** ORM gali išsiųsti `NULL`, o DB atmes su `IntegrityError`.

**Taisymas:** prirašyti `nullable=False` modeliuose (DB jau teisinga).

### P5 (žema) — `evidences.uploaded_by` neturi FK į `users.id`

**Modelis:** `backend/app/models/project.py` laukas `uploaded_by = Column(UUID_TYPE)` be `ForeignKey`.

**Migracija:** `backend/app/migrations/versions/20260203_000001_init_core_schema.py` `uploaded_by` yra UUID be FK.

**Poveikis:** nėra referencinio integralumo; galima turėti `uploaded_by`, kuris neegzistuoja.

**Taisymas:** pridėti FK (`ON DELETE SET NULL`) + modelyje pridėti `ForeignKey("users.id", ondelete="SET NULL")`.

### P6 (žema) — Settings dubliavimai / nenaudojami raktai

**Dubliavimas:** `backend/app/core/config.py` turi `DOCS_ENABLED`/`OPENAPI_ENABLED` ir atskirai `docs_enabled`/`openapi_enabled`. Realus naudojimas šiuo metu yra per `settings.DOCS_ENABLED` ir `settings.OPENAPI_ENABLED` (`backend/app/main.py`).

**Nenaudojami:** `audit_log_retention_days`, `enable_robot_adapter` (randami tik config'e, niekur nenaudojami).

**Taisymas:** susitarti dėl vieno kanoninio pavadinimo ir išvalyti dublikatus (su `validation_alias` jei reikia backward-compat).

### P7 (žema) — testai yra integration-style (reikia veikiančio serverio)

`backend/tests/conftest.py` naudoja `httpx.AsyncClient(base_url=BASE_URL)` ir pagal nutylėjimą tikisi serverio ant `http://127.0.0.1:8000`.

**Poveikis:** testų paleidimui reikia paleisti backend serverį (CI tai turi daryti).

**Taisymas (pageidautinas):** pridėti "app fixture" su ASGI transport (in-process), kad testai galėtų veikti be atskiro serverio.

## Prioritetinė taisymų eilė (rekomenduojama)

1. Nauja migracija: `chk_appointment_time` + NOT NULL backfill/set + `evidences.uploaded_by` FK (jei sutariam, kad tai kanoninė semantika).
2. Modelių suvienodinimas su DB: `lock_level` -> `SmallInteger`, `nullable=False` bool laukams.
3. Settings cleanup: pašalinti dubliavimus / pažymėti rezervuotus raktus.
4. (Optional) testų infrastruktūra: pereiti prie in-process ASGI client.

