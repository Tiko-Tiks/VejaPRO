# PILNAS SISTEMOS AUDITAS — ATASKAITA

Data: 2026-02-07

Verdiktas: sistema veikia stabiliai (CI "žalias", testai praeina), tačiau yra keli aiškūs "schema higienos" neatitikimai tarp SQLAlchemy modelių ir Alembic migracijų. Stuburas nepažeistas, bet šiuos drift'us verta sutvarkyti, kad DB taisyklės būtų kanoninės ir neatsirastų paslėptų IntegrityError ar neteisingų duomenų.

## Atnaujinimas (2026-02-08)

Šio audito P1–P5 punktai yra **išspręsti** (schema higiena sutvarkyta).

CI/Tests (stabilizacija):
- Webhook testai sutvirtinti: call_request patikra daroma tiesiogiai per DB (ne per `/admin/call-requests` list), kad nebūtų priklausomybės nuo pagination / sort order.
- Webhook testuose seeded'inamas bent vienas aktyvus `users` įrašas, kad Voice/Chat galėtų pasirinkti default `resource_id` (kai `SCHEDULE_DEFAULT_RESOURCE_ID` nėra nurodytas).

Įgyvendinta:
- **P1**: `appointments` gavo DB-level `chk_appointment_time` (`ends_at > starts_at`) per migraciją `backend/app/migrations/versions/20260208_000011_schema_hygiene_constraints.py`.
- **P2**: `Appointment.lock_level` suvienodintas: modelis naudoja `SmallInteger` (DB jau buvo `SmallInteger`).
- **P3**: `created_at`/`timestamp` drift'as sutvarkytas: backfill + `SET NOT NULL` (`users/margins/payments/sms_confirmations.created_at`, `audit_logs.timestamp`) per tą pačią migraciją.
- **P4**: bool laukams suvienodintas `nullable=False` modeliuose (DB jau buvo griežtas).
- **P5**: `evidences.uploaded_by` gavo FK į `users.id` (`ON DELETE SET NULL`) + duomenų cleanup per tą pačią migraciją; modelyje pridėtas `ForeignKey`.

Likę (ne schema higiena):
- **P6**: audite minėti settings dubliavimai dalinai buvo "stale": dabar naudojami kanoniniai `settings.docs_enabled`/`settings.openapi_enabled` su `AliasChoices("DOCS_ENABLED","docs_enabled")` ir `AliasChoices("OPENAPI_ENABLED","openapi_enabled")` (`backend/app/core/config.py`).
- **P7**: testai vis dar integration-style (reikalauja veikiancio serverio per `BASE_URL`). Tai nėra kritinė klaida, bet galima optimizacija.

## Kas patikrinta (high-level)

- CI disciplina: `lint` blokuoja (nėra `continue-on-error`), testai turi `needs: lint`.
- Schedule Engine: `no-overlap` semantika suvienodinta tarp SQLite (app-guard) ir Postgres (DB constraint).
- Admin UI: `/admin/calendar` turi "Hold įrankiai" ir "RESCHEDULE" testavimo blokus.

## SVEIKA (viskas gerai)

- Nėra sulaužytų importų, nėra akivaizdžių nuorodų į ištrintus modulius (CI lint praeina).
- Backend testų paketas veikia (CI `pytest` praeina).
- Schedule Engine overlap taisyklė atitinka spec: overlap blokuoja `HELD` + `CONFIRMED` visada (be expiry išimčių).

## PROBLEMOS (reikia taisyti)

### P1 (kritinė) — `chk_appointment_time` nėra DB migracijose (**IŠSPRĘSTA 2026-02-08**)

**Modelis:** `backend/app/models/project.py` turi `CheckConstraint("ends_at > starts_at", name="chk_appointment_time")` (Appointment `__table_args__`).

**Migracijos:**
- Pradinis `appointments` table sukūrimas `backend/app/migrations/versions/20260205_000003_add_call_calendar_tables.py` neturi jokio `CheckConstraint` `ends_at > starts_at`.
- Schedule Engine Phase 0 migracija `backend/app/migrations/versions/20260207_000007_schedule_engine_phase0.py` prideda `chk_appt_link` ir `chk_hold_only_when_held`, bet neprideda `chk_appointment_time`.

**Poveikis:** Postgres DB gali priimti `appointments` su `ends_at <= starts_at` (modelis/testai to "nemato", nes ORM turi constraint'ą, bet DB kanoniškai jo neturi).

**Taisymas:** nauja Alembic migracija, kuri prideda `chk_appointment_time` į `appointments` (ir downgrade nuima).

**STATUSAS:** išspręsta per `backend/app/migrations/versions/20260208_000011_schema_hygiene_constraints.py`.

### P2 (vidutinė) — `Appointment.lock_level` tipo neatitikimas (modelis vs migracija) (**IŠSPRĘSTA 2026-02-08**)

**Modelis:** `backend/app/models/project.py` turi `lock_level = Column(Integer, ...)`.

**Migracija:** `backend/app/migrations/versions/20260207_000007_schedule_engine_phase0.py` prideda `lock_level` kaip `SmallInteger`.

**Poveikis:** autogenerate drift + potencialus netikslumas. Semantiškai `lock_level` yra 0/1/2, todėl `SmallInteger` yra teisingas.

**Taisymas:** suvienodinti tipą (rekomenduojama: pakeisti modelį į `SmallInteger`, o DB palikti kaip `SmallInteger`).

**STATUSAS:** išspręsta (modelyje `SmallInteger`, DB jau buvo `SmallInteger`).

### P3 (vidutinė) — `created_at` / `timestamp` NOT NULL drift (**IŠSPRĘSTA 2026-02-08**)

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

**STATUSAS:** išspręsta per `backend/app/migrations/versions/20260208_000011_schema_hygiene_constraints.py`.

### P4 (žema) — atvirkštinis nullable drift (DB griežčiau nei ORM) (**IŠSPRĘSTA 2026-02-08**)

**DB (migracijoje):** `nullable=False`:
- `projects.has_robot`, `projects.is_certified` (`backend/app/migrations/versions/20260203_000001_init_core_schema.py`)
- `evidences.show_on_web`, `evidences.is_featured` (`backend/app/migrations/versions/20260203_000001_init_core_schema.py`)

**Modeliuose:** `nullable` nenurodyta (pagal nutylėjimą ORM leidžia `NULL`).

**Poveikis:** ORM gali išsiųsti `NULL`, o DB atmes su `IntegrityError`.

**Taisymas:** prirašyti `nullable=False` modeliuose (DB jau teisinga).

**STATUSAS:** išspręsta (modeliuose `nullable=False` bool'ams suvienodinta su DB).

### P5 (žema) — `evidences.uploaded_by` neturi FK į `users.id` (**IŠSPRĘSTA 2026-02-08**)

**Modelis:** `backend/app/models/project.py` laukas `uploaded_by = Column(UUID_TYPE)` be `ForeignKey`.

**Migracija:** `backend/app/migrations/versions/20260203_000001_init_core_schema.py` `uploaded_by` yra UUID be FK.

**Poveikis:** nėra referencinio integralumo; galima turėti `uploaded_by`, kuris neegzistuoja.

**Taisymas:** pridėti FK (`ON DELETE SET NULL`) + modelyje pridėti `ForeignKey("users.id", ondelete="SET NULL")`.

**STATUSAS:** išspręsta per `backend/app/migrations/versions/20260208_000011_schema_hygiene_constraints.py` + modelio korekcija.

### P6 (žema) — Settings dubliavimai / nenaudojami raktai

**Dubliavimas:** kanoninis naudojimas yra per `settings.docs_enabled` / `settings.openapi_enabled` (`backend/app/main.py`), o backward-compat per env aliasus yra per `AliasChoices("DOCS_ENABLED","docs_enabled")` ir `AliasChoices("OPENAPI_ENABLED","openapi_enabled")` (`backend/app/core/config.py`).

**Nenaudojami / pašalinti:** ankstesni "audit_log_retention_days"/"enable_robot_adapter" raktai buvo paminėti audito metu kaip potencialiai stale. Jei dokumentacijoje jie dar minimi, tai yra **DOCS cleanup** užduotis (kodo konfig'e šiuo metu jie nebenaudojami).

**Taisymas:** susitarti dėl vieno kanoninio pavadinimo ir išvalyti dublikatus (su `validation_alias` jei reikia backward-compat).

### P7 (žema) — testai yra integration-style (reikia veikiančio serverio)

`backend/tests/conftest.py` naudoja `httpx.AsyncClient(base_url=BASE_URL)` ir pagal nutylėjimą tikisi serverio ant `http://127.0.0.1:8000`.

**Poveikis:** testų paleidimui reikia paleisti backend serverį (CI tai turi daryti).

**Taisymas (pageidautinas):** pridėti "app fixture" su ASGI transport (in-process), kad testai galėtų veikti be atskiro serverio.

## Prioritetinė taisymų eilė (rekomenduojama)

1. (DONE) Schema higiena: `chk_appointment_time` + NOT NULL backfill/set + `evidences.uploaded_by` FK.
2. (DONE) Modelių suvienodinimas su DB: `lock_level` -> `SmallInteger`, `nullable=False` bool laukams.
3. Docs cleanup: pašalinti / pažymėti stale settings dokumentacijoje (pvz. `ENABLE_ROBOT_ADAPTER`).
4. (Optional) testų infrastruktūra: pereiti prie in-process ASGI client.
5. Schedule Engine užbaigimas: Voice konfliktų valdymas (409 -> siūlyti kitą slotą) + concurrency/race testai.
