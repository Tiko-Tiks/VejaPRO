# Schedule Engine V1.1.1 - FINAL (Unified RESCHEDULE, Consistency Patch A-1)

Data: 2026-02-07  
Statusas: LOCKED  
Lygis: L2 modulis (ijungiamas tik per feature flag)  
Suderinimas: suderinta su Core Domain (statusai nelieciami, forward-only, backend = vienas tiesos saltinis, audit privalomas).

Nuorodos:
- `backend/VEJAPRO_KONSTITUCIJA_V1.3.md`
- `backend/VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md`
- `backend/VEJAPRO_V1.52_SUMMARY.md`
- `backend/requirements.txt`

## 0) Paskirtis

Schedule Engine valdo tik vizitu planavima (`appointments`).

Jis:
- uztikrina, kad patvirtinti laikai nebutu automatiskai stumdomi;
- sprendzia konkurencinguma (Voice/Chat) per laikinas rezervacijas (`HELD`);
- leidzia operatoriui vienu UI veiksmu perdelioti grafika (`RESCHEDULE`) del bet kokios priezasties;
- po operatoriaus patvirtinimo automatiskai sutvarko komunikacija ir galutini fiksavima.

## 1) Nekintami principai

### 1.1 Statusu asis nelieciama

`projects.status` leidziami tik:
- `DRAFT`
- `PAID`
- `SCHEDULED`
- `PENDING_EXPERT`
- `CERTIFIED`
- `ACTIVE`

Jokiu nauju statusu planavimui.

### 1.2 Vienintelis tiesos saltinis - backend

Visi lock'ai, hold'ai, `no overlap`, `RESCHEDULE` - tik backend'e. Frontend/AI tik siulo.

### 1.3 Audit privalomas

Kritiniai planavimo veiksmai rasomi i `audit_logs` kanoniniu formatu.

### 1.4 Forward-only planavime

`RESCHEDULE` nera `UPDATE` i `CONFIRMED` laika.  
`RESCHEDULE` = `CANCEL + CREATE` (su superseded chain).

### 1.5 Feature flags

- `ENABLE_SCHEDULE_ENGINE=false`

Nera atskiro weather flag - weather automatika isimta.

## 2) Terminai ir roles

### 2.1 Objektai

- `Project`: Core Domain procesas.
- `Appointment`: vizitas (planavimo asis).

### 2.2 Aktoriai (audit'e) - tik kanoniniai

Leidziami `actor_type`:
- `SYSTEM_STRIPE`
- `SYSTEM_TWILIO`
- `CLIENT`
- `SUBCONTRACTOR`
- `EXPERT`
- `ADMIN`

Jokiu nauju `actor_type`. Sistemos kilmes kontekstas (pvz. worker/scheduler) fiksuojamas `metadata.system_source`, o `actor_type` lieka kanoninis (dažniausiai `SUBCONTRACTOR/ADMIN`, nes tai operatoriaus inicijuoti veiksmai).

## 3) Duomenu modelis (DB)

### 3.1 `appointments` (kanonine lentele)

Pastaba:
- `project_id` gali buti `NULL` tik tada, jei sistemoje egzistuoja `call_requests` ir naudojamas `call_request_id`.
- Jei `call_requests` modelio nera - `call_request_id` salinamas, o `project_id` daromas `NOT NULL`.

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

DO $$ BEGIN
    CREATE TYPE appointment_status AS ENUM ('HELD','CONFIRMED','CANCELLED');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE weather_class AS ENUM ('SOIL_SENSITIVE','WEATHER_RESISTANT','MIXED');
EXCEPTION WHEN duplicate_object THEN null; END $$;

CREATE TABLE appointments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Vienas is dvieju turi buti: project_id arba call_request_id
    project_id          UUID NULL REFERENCES projects(id) ON DELETE SET NULL,
    call_request_id     UUID NULL REFERENCES call_requests(id) ON DELETE SET NULL,

    resource_id         UUID NOT NULL REFERENCES users(id),
    visit_type          VARCHAR(32) NOT NULL DEFAULT 'PRIMARY',

    starts_at           TIMESTAMPTZ NOT NULL,
    ends_at             TIMESTAMPTZ NOT NULL,
    status              appointment_status NOT NULL,

    lock_level          SMALLINT NOT NULL DEFAULT 0,
    locked_at           TIMESTAMPTZ NULL,
    locked_by           UUID NULL REFERENCES users(id),
    lock_reason         TEXT NULL,

    hold_expires_at     TIMESTAMPTZ NULL,
    weather_class       weather_class NOT NULL,

    route_date          DATE NULL,
    route_sequence      INTEGER NULL,

    row_version         INTEGER NOT NULL DEFAULT 1,
    superseded_by_id    UUID NULL REFERENCES appointments(id),

    cancelled_at        TIMESTAMPTZ NULL,
    cancelled_by        UUID NULL REFERENCES users(id),
    cancel_reason       TEXT NULL,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_appointment_time CHECK (ends_at > starts_at),
    CONSTRAINT chk_appt_link CHECK (project_id IS NOT NULL OR call_request_id IS NOT NULL),
    CONSTRAINT chk_hold_only_when_held CHECK (
        (status = 'HELD' AND hold_expires_at IS NOT NULL)
        OR
        (status <> 'HELD' AND hold_expires_at IS NULL)
    )
);

-- Vienas CONFIRMED per project + visit_type (tik kai project_id ne NULL)
CREATE UNIQUE INDEX uniq_project_confirmed_visit
ON appointments(project_id, visit_type)
WHERE status = 'CONFIRMED' AND project_id IS NOT NULL;

-- No-overlap per resursa (HELD+CONFIRMED)
ALTER TABLE appointments
ADD CONSTRAINT no_overlap_per_resource
EXCLUDE USING gist (
    resource_id WITH =,
    tstzrange(starts_at, ends_at, '[)') WITH &&
)
WHERE (status IN ('HELD','CONFIRMED'));

-- Indeksai
CREATE INDEX idx_appt_resource_time ON appointments(resource_id, starts_at);
CREATE INDEX idx_appt_project_time  ON appointments(project_id, starts_at);
CREATE INDEX idx_appt_route         ON appointments(route_date, resource_id, route_sequence);
CREATE INDEX idx_appt_hold_exp      ON appointments(hold_expires_at) WHERE status='HELD';
```

### 3.2 `conversation_locks` (Voice/Chat mapping)

Papildomas saugiklis:
- saugoti ir `visit_type`, kad ateityje (PRIMARY/CERTIFICATION/FOLLOW_UP) Voice/Chat nepatvirtintu ne to vizito.

```sql
DO $$ BEGIN
    CREATE TYPE conversation_channel AS ENUM ('VOICE','CHAT');
EXCEPTION WHEN duplicate_object THEN null; END $$;

CREATE TABLE conversation_locks (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel           conversation_channel NOT NULL,
    conversation_id   VARCHAR(128) NOT NULL,
    appointment_id    UUID NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,
    visit_type        VARCHAR(32) NOT NULL DEFAULT 'PRIMARY',
    hold_expires_at   TIMESTAMPTZ NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uniq_conversation_lock UNIQUE (channel, conversation_id)
);

CREATE INDEX idx_conv_lock_exp ON conversation_locks(hold_expires_at);
CREATE INDEX idx_conv_lock_visit ON conversation_locks(appointment_id, visit_type);
```

### 3.3 `project_scheduling` (backlog/readiness)

```sql
CREATE TABLE project_scheduling (
    project_id              UUID PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    ready_to_schedule       BOOLEAN NOT NULL DEFAULT FALSE,
    default_weather_class   weather_class NOT NULL,
    estimated_duration_min  INTEGER NOT NULL,
    priority_score          INTEGER NOT NULL DEFAULT 0,
    preferred_time_windows  JSONB NULL,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sched_ready ON project_scheduling(ready_to_schedule, priority_score DESC);
```

Pastaba: `weather_risk` ir `last_weather_check_at` nera (automatika isimta).

## 4) `projects.scheduled_for` (backward compatibility)

`projects.scheduled_for` lieka kaip denormalizuotas laukas UI/legacy flow'ams.

Valdymo taisykle:
- `scheduled_for` atspindi tik `visit_type='PRIMARY' AND status='CONFIRMED' AND project_id IS NOT NULL` vizito `starts_at`.

Valdymo variantai:
1. `MVP`: serviso sluoksnyje (greitesnis startas, daugiau disciplinos kode).
2. `Rekomenduojamas stabilizavimui`: DB triggeris `sync_project_scheduled_for()` tik denormalizuotam laukui.

Pastaba apie audit:
- audit lieka appointment ivykiu lygyje;
- `projects.scheduled_for` yra techninis denormalizuotas laukas ir nera atskiras verslo ivykis.

## 5) Lock asis (Stability Lock)

### 5.1 Lock lygiai

- `0`: laisvas
- `1`: WEEK - patvirtinta klientui
- `2`: DAY - patvirtinta diena (batch)

### 5.2 Backend uztvara

- `CONFIRMED` laiko keitimas per `UPDATE` draudziamas visada.
- `lock_level >= 2`: tik `ADMIN` gali `RESCHEDULE` (su privalomu reason + audit).
- `lock_level == 1`: `SUBCONTRACTOR/ADMIN` gali `RESCHEDULE` (su reason + audit).

## 6) Voice-Hold (konkurencingumas)

### 6.1 Konfig

- `HOLD_DURATION_MINUTES=3`

### 6.2 Hold kurimas

Kai Voice/Chat "istaria" laika:
- `INSERT` i `appointments` su `status=HELD`, `hold_expires_at`;
- `INSERT` i `conversation_locks`.

Jei `no_overlap` constraint meta klaida:
- slotas uzimtas;
- siulomas kitas.

### 6.3 Confirm ("Tinka")

- surandamas `appointment_id` per `conversation_locks`;
- papildomai tikrinama, kad lock'o `visit_type` sutampa su appointment `visit_type`;
- tikrinama: `status=HELD` ir `hold_expires_at > now`;
- `UPDATE`: `status -> CONFIRMED`, `hold_expires_at -> NULL`, `lock_level -> 1`, `row_version=row_version+1`;
- audit: `APPOINTMENT_CONFIRMED`;
- jei `project_id IS NOT NULL AND visit_type='PRIMARY'` -> atnaujinti `projects.scheduled_for`.

### 6.4 Expiry worker

Daznis: kas 1 min.

Taisykle:
- cancelinti tik `HELD`, kuriu `hold_expires_at < now()`;
- `status -> CANCELLED`, `cancel_reason="HOLD_EXPIRED"`, `hold_expires_at=NULL`, `row_version=row_version+1`.

Audit neprivalomas.

### 6.5 Hold API (Phase 2)

Admin/Operator (laikinai) naudojami endpointai, kad Voice/Chat galetu atomiskai rezervuoti slota dar pokalbio metu:

- `POST /api/v1/admin/schedule/holds` (create HELD + conversation_lock)
- `POST /api/v1/admin/schedule/holds/confirm` (HELD -> CONFIRMED + lock_level=1)
- `POST /api/v1/admin/schedule/holds/cancel` (HELD -> CANCELLED)
- `POST /api/v1/admin/schedule/holds/expire` (admin-only, HELD expired -> CANCELLED)

Pastaba:
- `expire` yra techninis endpointas (skirtas timeriui). Audit jam neprivalomas.

## 7) Oru automatika - PASALINTA

Kanonine taisykle:
- sistema niekada pati nesiulo perplanavimo "nes rytoj lis";
- nera Weather Check Job;
- nera oru API integracijos;
- nera risk flag'u.

Oras yra tik viena is operatoriaus ivestu `RESCHEDULE` priezasciu (zr. 8 skyriu).

## 8) Unified RESCHEDULE (vienas mechanizmas visoms priezastims)

### 8.1 Priezastys (tik auditui/komunikacijai, ne logikai)

`RESCHEDULE_REASON`:
- `WEATHER`
- `TECHNICAL_ISSUE`
- `RESOURCE_UNAVAILABLE`
- `TIME_OVERFLOW`
- `OTHER`

Sis laukas nekeicia algoritmo.

### 8.2 Vienas UI veiksmas, dvieju faziu backend

UI turi viena mygtuka: `RESCHEDULE`.

Backend'e:
1. `preview` (pasiulymas);
2. `confirm` (mutacijos).

Tai privaloma, kad nebutu negriztamu `CANCEL/CREATE` be perziuros.

## 9) RESCHEDULE API (kanonine)

### 9.0 Preview state valdymo rezimai

Leidziami 2 rezimai:
1. `Server-side preview` (default, saugiausias):
   - preview saugomas serveryje su TTL.
2. `Stateless preview` (MVP alternatyva):
   - UI i `confirm` grazina ta pati `suggested_actions` + `preview_hash`;
   - backend validuoja hash ir `row_version`.

Abiem atvejais:
- be galiojancio hash/preview `confirm` nevykdo mutaciju.
- hash skaiciavimo algoritmas ir kanoninis JSON serializavimas turi buti fiksuoti implementacijoje.

### 9.1 `POST /api/v1/admin/schedule/reschedule/preview`

Kas gali: `SUBCONTRACTOR`, `ADMIN`.

Request:

```json
{
  "route_date": "2026-02-10",
  "resource_id": "uuid",
  "scope": "DAY",
  "reason": "WEATHER",
  "comment": "Per slapia dirva - siandien sejos nevykdom",
  "rules": {
    "preserve_locked_level": 1,
    "allow_replace_with_weather_resistant": true
  }
}
```

Response (privalomi saugikliai):

```json
{
  "preview_id": "uuid",
  "preview_hash": "sha256hex",
  "preview_expires_at": "2026-02-10T08:30:00Z",
  "original_appointment_ids": ["..."],
  "suggested_actions": [
    {"action": "CANCEL", "appointment_id": "..."},
    {
      "action": "CREATE",
      "project_id": "...",
      "visit_type": "PRIMARY",
      "resource_id": "...",
      "starts_at": "...",
      "ends_at": "...",
      "weather_class": "WEATHER_RESISTANT"
    }
  ],
  "summary": {
    "cancel_count": 3,
    "create_count": 3,
    "total_travel_minutes": 87
  }
}
```

Preview saugiklis:
- preview saugomas server-side su TTL (pvz. 15 min);
- `preview_hash` skaiciuojamas nuo `(route_date, resource_id, original_appointment_ids, suggested_actions)`;
- be galiojancio preview `confirm` negali vykdyti mutaciju.
- jei naudojamas stateless rezimas, `confirm` gauna `suggested_actions` ir backend perskaiciuoja hash.

### 9.2 `POST /api/v1/admin/schedule/reschedule/confirm`

Kas gali: `SUBCONTRACTOR`, `ADMIN`.

Taikomos lock taisykles.

Request:

```json
{
  "preview_id": "uuid",
  "preview_hash": "sha256hex",
  "reason": "WEATHER",
  "comment": "Per slapia dirva",
  "expected_versions": {
    "appt_id_1": 3,
    "appt_id_2": 5
  }
}
```

Veiksmai (viena DB transakcija):
1. validuoti `preview_id + preview_hash + preview_expires_at`;
2. patikrinti, kad original appointment'ai vis dar tie patys (`row_version` pagal `expected_versions`);
3. `CANCEL` original:
   - `status=CANCELLED`,
   - `cancelled_at=now`,
   - `cancel_reason="RESCHEDULE:<REASON>"`,
   - `cancelled_by=current_user.id`,
   - `row_version=row_version+1`;
4. `CREATE` naujus `CONFIRMED`:
   - `status=CONFIRMED`,
   - `lock_level=1`,
   - jei 1:1 mapping - pildyti `superseded_by_id` senajame irase,
   - jei N:1 - mapping deti i audit metadata;
5. update `projects.scheduled_for` (`PRIMARY`, tik jei `project_id IS NOT NULL`);
6. audit (privaloma):
   - `SCHEDULE_RESCHEDULED` (batch),
   - `APPOINTMENT_CANCELLED` kiekvienam atsauktam,
   - `APPOINTMENT_CONFIRMED` kiekvienam sukurtam;
   - visuose 3 ivykiuose `metadata` turi tureti:
     - `reason`
     - `comment`
     - `reschedule_preview_id` (jei taikoma);
7. klientu pranesimai:
   - enqueue (idempotentiskai) apie nauja laika.

Response:

```json
{
  "success": true,
  "new_appointment_ids": ["..."],
  "notifications_enqueued": true
}
```

## 10) Daily Batch Approve

Nepakeista:
- `lock_level=2` rytojaus patvirtinimui;
- audit metadata privaloma.

### 10.1 Daily Approve API (Phase 3)

- `POST /api/v1/admin/schedule/daily-approve`

Semantika:
- suranda pasirinktos dienos (`route_date`) ir resurso (`resource_id`) `CONFIRMED` vizitus;
- uzdeda `lock_level=2` (DAY) ir padidina `row_version`;
- sukuria audit:
  - `APPOINTMENT_LOCK_LEVEL_CHANGED` (kiekvienam pakeistam vizitui),
  - `DAILY_BATCH_APPROVED` (schedule_day batch ivykis).

## 11) Audit katalogas (kanoninis)

Entity: `appointment`
- `APPOINTMENT_CONFIRMED`
- `APPOINTMENT_CANCELLED`
- `APPOINTMENT_LOCK_LEVEL_CHANGED`

Entity: `schedule_day` (pseudo entity leidziama audit'e)
- `SCHEDULE_RESCHEDULED`
- `DAILY_BATCH_APPROVED`

### 11.1 `schedule_day.entity_id` deterministine schema (PRIVALOMA)

Kad butu galima filtruoti audit'e pagal diena/resursa, `entity_id` turi buti deterministinis:

`UUIDv5(namespace=SCHEDULE_DAY_NAMESPACE_UUID, name=f"{route_date}:{resource_id}")`

`SCHEDULE_DAY_NAMESPACE_UUID` turi buti viena nekintama projekto konstanta.

`actor_type`: tik kanoniniai.

## 12) Testavimo minimumas

DB:
- `no_overlap` (race test)
- `uniq_project_confirmed_visit`
- `hold constraint`

Concurrency:
- hold/confirm race
- preview hash mismatch -> `409`
- hold expiry race (confirm po expiry) -> `409` arba `410`

RESCHEDULE:
- row_version conflict -> `409`
- `lock_level>=2` -> tik `ADMIN`
- stale preview (expired) -> `409`
- `projects.scheduled_for` sinchronizacija po keliu `CONFIRMED/CANCELLED` ciklu

## 12.1 Mokejimu suderinamumas (Stripe + grynieji)

Schedule Engine nekeicia Core payment flow ir neliecia finansiniu ivykiu.

Taisykles:
- `RESCHEDULE` negali trinti/keisti `payments` ir statusu;
- komunikacijoje galima rodyti atsiskaitymo metoda, bet tai UI/notification layer, ne planavimo logika;
- `CERTIFIED -> ACTIVE` lieka Core modulyje per kanoninius trigger'ius.

## 13) Rollout

- Phase 0: DB + API, flags off
- Phase 1: Admin UI su preview/confirm RESCHEDULE
- Phase 1.1: Admin UI greiti `RESCHEDULE reason` mygtukai:
  - "Lijo / per slapia"
  - "Techninis gedimas"
  - "Rangovas nespejo"
  - "Klientas paprase perkelti"
  - "Kita" (su komentaru)
- Phase 2: Voice-Hold
- Phase 3: Daily approve

## 13.1) Implementacijos statusas (2026-02-07)

Siame etape pradeta reali backend implementacija (Phase 0):
- prideti konfig raktai (`ENABLE_SCHEDULE_ENGINE`, `HOLD_DURATION_MINUTES`, `SCHEDULE_PREVIEW_TTL_MINUTES`, `SCHEDULE_USE_SERVER_PREVIEW`, `SCHEDULE_DAY_NAMESPACE_UUID`);
- sukurti modeliai: `conversation_locks`, `project_scheduling`, `schedule_previews`, ir isplestas `appointments` modelis;
- sukurti endpoint'ai:
  - `POST /api/v1/admin/schedule/reschedule/preview`
  - `POST /api/v1/admin/schedule/reschedule/confirm`
- idiegti saugikliai:
  - HMAC `preview_hash` validacija,
  - `row_version` tikrinimas,
  - `lock_level>=2` leidimas tik `ADMIN`,
  - deterministinis `schedule_day.entity_id` (`UUIDv5`);
- idiegti audit ivykiai:
  - `APPOINTMENT_CANCELLED`,
  - `APPOINTMENT_CONFIRMED`,
  - `SCHEDULE_RESCHEDULED`,
  su `metadata.reason`, `metadata.comment`, `metadata.reschedule_preview_id`.

Liko kitoms fazems:
- Voice-Hold pilnas runtime srautas (hold create/confirm/expiry endpoint'ai ir worker'is);
- Daily Batch Approve UI;
- klientu notifikaciju outbox worker'is;
- papildomi konkurenciniai ir race testai.

## 14) Galutine taisykle

Bet koks neivykes darbas (oras / gedimas / nespejom) tvarkomas vienu mechanizmu: `RESCHEDULE` (`preview -> confirm`), o priezastis naudojama tik auditui ir komunikacijai, ne elgsenai.
