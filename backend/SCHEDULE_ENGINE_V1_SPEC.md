# Schedule Engine V1.1.1 - FINAL (Unified RESCHEDULE, Consistency Patch A)

Data: 2026-02-07  
Statusas: LOCKED  
Lygis: L2 modulis (ijungiamas tik per feature flag)  
Suderinimas: suderinta su Core Domain - statusai nelieciami, forward-only, backend yra vienas tiesos saltinis, audit privalomas.

Nuorodos:
- `backend/VEJAPRO_KONSTITUCIJA_V1.3.md`
- `backend/VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.md`
- `backend/VEJAPRO_V1.52_SUMMARY.md`
- `backend/requirements.txt`

## 0) Paskirtis

Schedule Engine valdo tik vizitu planavima (`appointments`).

Jis:
- uztikrina, kad patvirtinti laikai nebutu automatiskai stumdomi;
- sprendzia konkurencinguma (Voice/Chat);
- leidzia operatoriui vienu veiksmu perdelioti grafika (`RESCHEDULE`) del bet kokios priezasties;
- automatiskai sutvarko komunikacija ir galutini fiksavima po operatoriaus patvirtinimo.

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

Nera atskiro weather flag, nes weather automatika isimta (zr. 7 skyriu).

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

Jokiu nauju `actor_type` (pvz. `SYSTEM_WEATHER`).
Sistemos kilmes kontekstas fiksuojamas `metadata.system_source`, ne naujais actor_type.

## 3) Duomenu modelis (DB)

### 3.1 `appointments` (kanonine lentele)

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

-- Vienas CONFIRMED per project + visit_type
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

```sql
DO $$ BEGIN
    CREATE TYPE conversation_channel AS ENUM ('VOICE','CHAT');
EXCEPTION WHEN duplicate_object THEN null; END $$;

CREATE TABLE conversation_locks (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel           conversation_channel NOT NULL,
    conversation_id   VARCHAR(128) NOT NULL,
    appointment_id    UUID NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,
    hold_expires_at   TIMESTAMPTZ NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uniq_conversation_lock UNIQUE (channel, conversation_id)
);

CREATE INDEX idx_conv_lock_exp ON conversation_locks(hold_expires_at);
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

Pastaba: `weather_risk` ir `last_weather_check_at` pasalinta, nes weather automatika ir weather rezimas isimti.

## 4) `projects.scheduled_for` (backward compatibility)

`projects.scheduled_for` lieka kaip denormalizuotas laukas UI/legacy flow'ams.

Valdymo taisykle:
- `scheduled_for` atspindi tik `visit_type='PRIMARY' AND status='CONFIRMED' starts_at`.

Valdoma serviso sluoksnyje (ne DB trigger'iu), kad isliktu aiski audit logika ir isvengti tylu DB side-effect'u.

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
- tikrinama: `status=HELD` ir `hold_expires_at > now`;
- `UPDATE`: `status -> CONFIRMED`, `hold_expires_at -> NULL`, `lock_level -> 1`;
- audit: `APPOINTMENT_CONFIRMED`;
- atnaujinti `projects.scheduled_for` (`PRIMARY`).

### 6.4 Expiry worker

Kas 1 min:
- `HELD` expired -> `CANCELLED` (`cancel_reason="HOLD_EXPIRED"`).

Audit siam veiksmui neprivalomas.

## 7) Oru automatika - PASALINTA (samoningai)

Kanonine taisykle:
- sistema niekada pati nesiulo perplanavimo "nes rytoj lis";
- nera Weather Check Job;
- nera oru API integracijos;
- nera risk flag'u.

Oras yra tik viena is operatoriaus ivestu `RESCHEDULE` priezasciu (zr. 8 skyriu).

## 8) Unified RESCHEDULE (vienas veiksmas visoms priezastims)

### 8.1 Priezastys (tik auditui/komunikacijai, ne logikai)

`RESCHEDULE_REASON`:
- `WEATHER`
- `TECHNICAL_ISSUE`
- `RESOURCE_UNAVAILABLE`
- `TIME_OVERFLOW`
- `OTHER`

Svarbu: sis laukas nekeicia algoritmo - algoritmas visada tas pats.

### 8.2 RESCHEDULE yra dvieju faziu, bet vienas operatoriaus veiksmas UI

UI turi viena mygtuka:
- `RESCHEDULE day / reschedule affected visits`

Backend'e vyksta 2 etapai:
1. preview (generuoti pasiulyma);
2. confirm (apply).

Tai butina, kad neivyktu negriztami `CANCEL/CREATE` be zmogaus perziuros.

## 9) RESCHEDULE API (kanonine)

### 9.1 `POST /api/v1/admin/schedule/reschedule/preview`

Kas gali:
- `SUBCONTRACTOR`
- `ADMIN`

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

Semantika:
- `scope=DAY`: perdelioti tos dienos plana tam resursui.
- `preserve_locked_level=1`: nelieciame `lock>=1` vizitu automatiskai (tik atvaizduojame kaip nepajudinama).

Response:

```json
{
  "preview_id": "uuid",
  "preview_hash": "sha256hex",
  "preview_expires_at": "2026-02-10T08:30:00Z",
  "original_appointment_ids": ["..."],
  "suggested_actions": [
    {
      "action": "CANCEL",
      "appointment_id": "..."
    },
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
- preview rezultatas server-side issaugomas su TTL (pvz. 15 min);
- `preview_hash` skaiciuojamas nuo `suggested_actions + original_appointment_ids + route_date + resource_id`;
- be galiojancio preview `confirm` negali vykdyti mutaciju.

### 9.2 `POST /api/v1/admin/schedule/reschedule/confirm`

Kas gali:
- `SUBCONTRACTOR`
- `ADMIN`

Taikomos lock taisykles.

Request:

```json
{
  "preview_id": "uuid",
  "preview_hash": "sha256hex",
  "route_date": "2026-02-10",
  "resource_id": "uuid",
  "reason": "WEATHER",
  "comment": "Per slapia dirva",
  "original_appointment_ids": ["..."],
  "expected_versions": {
    "appt_id_1": 3,
    "appt_id_2": 5
  },
  "suggested_actions": []
}
```

Veiksmai (atomine transakcija):
1. validuoti `preview_id + preview_hash + preview_expires_at`;
2. patikrinti, kad original appointment'ai vis dar tie patys (`row_version`);
3. `CANCEL` original:
   - `status=CANCELLED`
   - `cancelled_at=now`
   - `cancel_reason="RESCHEDULE:<REASON>"`
4. `CREATE` naujus `CONFIRMED`:
   - `status=CONFIRMED`
   - `lock_level=1` (WEEK)
   - superseded chain:
     - 1:1 mapping -> `superseded_by_id`;
     - jei N:1 -> saugoti metadata.
5. update `projects.scheduled_for` (`PRIMARY`) pagal nauja `CONFIRMED`.
6. audit (privaloma):
   - `SCHEDULE_RESCHEDULED` (entity_type `schedule_day` arba `appointment` su batch metadata)
   - `APPOINTMENT_CANCELLED` (uz kiekviena atsaukta)
   - `APPOINTMENT_CONFIRMED` (uz kiekviena nauja)
7. klientu pranesimai:
   - isiusti pranesima apie nauja laika (idempotentiskai).

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

## 11) Audit katalogas (kanoninis)

Entity: `appointment`
- `APPOINTMENT_CONFIRMED`
- `APPOINTMENT_CANCELLED`
- `APPOINTMENT_LOCK_LEVEL_CHANGED`

Entity: `schedule_day`  
(pseudo entity leidziama audit'e, bet `entity_id` turi buti deterministic UUIDv5 is `route_date + resource_id`)
- `SCHEDULE_RESCHEDULED`
- `DAILY_BATCH_APPROVED`

`actor_type`: tik kanoniniai.

## 12) Testavimo minimumas

DB:
- `no_overlap`
- `uniq_project_confirmed_visit`
- `hold constraint`

Concurrency:
- race hold/confirm
- preview hash mismatch -> `409`

RESCHEDULE:
- `row_version` conflict -> `409`
- `lock_level>=2` -> tik `ADMIN`
- stale preview (expired) -> `409`

## 12.1 Mokejimo suderinamumas (Stripe + grynieji)

Planavimo variklis nekeicia Core payment flow, bet privalo islaikyti suderinamuma:
- `RESCHEDULE` negali trinti/keisti finansiniu ivykiu;
- jei projektas pazymetas kaip grynuju atsiskaitymas, kliento pranesimuose rodomas atsiskaitymo metodas;
- aktyvacijos taisykles (`CERTIFIED -> ACTIVE`) lieka Core modulyje.

## 13) Rollout

- Phase 0: DB + API, flags off
- Phase 1: Admin UI su preview/confirm RESCHEDULE
- Phase 2: Voice-Hold
- Phase 3: Daily approve

## 14) Galutine taisykle

Bet koks neivykes darbas (oras / gedimas / nespejom) tvarkomas vienu mechanizmu: `RESCHEDULE` (`preview -> confirm`), o priezastis naudojama tik auditui ir komunikacijai, ne elgsenai.

