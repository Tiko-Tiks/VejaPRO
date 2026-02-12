# Security + Migration Auditas (2026-02-12)

## Scope

- Kodas: `backend/app`, `backend/app/static`, `backend/app/migrations/versions`
- Kriterijai:
  - Security Reviewer (10 kategoriju)
  - Migration Reviewer (6 kategorijos)

## Security Findings

### CRITICAL

- Nera.

### HIGH

- Nera.

### MEDIUM

1. CORS gali buti per platus, jei env nustatytas `*`:
   - Failas: `backend/app/core/config.py:609`
   - Kategorija: CORS/CSP
   - Statusas: PARTIAL FIX
   - Kas padaryta: prideta konfig validacija (`CORS_ALLOW_ORIGINS must not contain '*' when credentials are enabled`).
   - Kas liko: tai siuo metu warning-level validacija (app nestabdo startup automatinai).
   - Fix pasiulymas: failinti startup (`RuntimeError`) kai aptinkamas `*` su credentials.

2. Admin token endpoint apsauga priklauso nuo vieno shared secret:
   - Failas: `backend/app/api/v1/projects.py:690`, `backend/app/api/v1/projects.py:695`
   - Kategorija: Auth bypass
   - Statusas: HARDENED
   - Kas padaryta: endpointas papildytas `X-Admin-Token-Secret`, validacija su `hmac.compare_digest`, klaidos grazina 404.
   - Kas liko: jei secret nuteketu, galima isduoti ADMIN JWT.
   - Fix pasiulymas: riboti per IP allowlist + trumpas TTL + secret rotation.

### LOW

1. No-reply adresas buvo loguojamas pilnu email:
   - Failas: `backend/app/services/email_auto_reply.py:158`
   - Kategorija: Sensitive data in logs
   - Statusas: FIXED
   - Kas padaryta: pridetas `_redact_email_for_log()` (`backend/app/services/email_auto_reply.py:60`).

## Security Checklist (10 kategoriju) - Rezultatas

1. PII exposure: FIXED
   - `backend/app/static/calls.html:345`, `backend/app/static/calls.html:346`, `backend/app/static/calls.html:372`
   - Naudojami `maskPhone()` / `maskEmail()`.
2. SQL injection: OK
   - Aptiktos `text(...)` uzklausos su parametrais (`:mid`, `:hash`), f-string SQL nerasta.
3. Auth bypass: HARDENED
   - `backend/app/api/v1/client_views.py:214` dabar reikalauja `require_roles("CLIENT")` (`backend/app/api/v1/client_views.py:216`).
4. Feature flag leaks: OK
   - Isjungti moduliai daugumoje endpointu grazina 404.
5. Stripe webhook validation: OK
   - `stripe.Webhook.construct_event(...)` naudojamas su signature.
6. CORS/CSP: PARTIAL
   - CSP antrastes yra, CORS wildcard turi warning-level apsauga.
7. Input validation: FIXED/PARTIAL
   - Pakeisti `dict` payload i Pydantic:
     - `backend/app/schemas/project.py:255` (`SeedCertPhotosRequest`)
     - `backend/app/schemas/project.py:259` (`AdminConfirmRequest`)
     - `backend/app/api/v1/projects.py:1702`, `backend/app/api/v1/projects.py:1954`
8. Error responses: HARDENED
   - Deploy webhook nebeeksponuoja script output pagal nutylejima (`backend/app/api/v1/deploy.py:55`, `backend/app/api/v1/deploy.py:60`).
9. Actor RBAC: OK
   - `_is_allowed_actor()` taikomas transition path'e.
10. Sensitive data in logs: HARDENED
   - WhatsApp telefono redakcija:
     - `backend/app/services/notification_outbox_channels.py:31`
     - `backend/app/services/notification_outbox_channels.py:182`

## Migration Findings

### CRITICAL (blokuoja deploy)

- Nera.

### WARNING

1. PostgreSQL-specific introspection be sqlite guard:
   - Failas: `backend/app/migrations/versions/20260209_000016_v23_finance_reconstruction.py:37`, `backend/app/migrations/versions/20260209_000016_v23_finance_reconstruction.py:47`
   - Kategorija: PostgreSQL/SQLite suderinamumas
   - Rizika: sqlite aplinkoje gali nebuti `pg_indexes` / `information_schema`.
   - Fix pasiulymas: tikrinti `dialect == "postgresql"` pries PG katalogu uzklausas.

2. PG-only tipai be sqlite fallback:
   - Failas: `backend/app/migrations/versions/20260211_000017_service_requests.py:26`, `backend/app/migrations/versions/20260211_000017_service_requests.py:31`
   - Kategorija: PostgreSQL/SQLite suderinamumas
   - Rizika: sqlite migracija neperbega, jei naudojamas Alembic su sqlite.
   - Fix pasiulymas: conditional type branch (`postgresql.UUID/JSONB` vs `sa.CHAR(36)/sa.JSON()`).

3. Index lock rizika ant dideliu lenteliu:
   - Failas: `backend/app/migrations/versions/20260209_000016_v23_finance_reconstruction.py:94`
   - Kategorija: Performance impact
   - Rizika: `CREATE UNIQUE INDEX` gali lock'inti rasyma.
   - Fix pasiulymas: `CREATE INDEX CONCURRENTLY` (su atitinkamom Alembic/aplinkos salygom).

4. Downgrade gali failinti del duomenu:
   - Failas: `backend/app/migrations/versions/20260209_000015_unified_client_card_v22.py:221`
   - Kategorija: Schema safety
   - Rizika: `SET NOT NULL` ant `evidences.project_id` grius jei yra `NULL`.
   - Fix pasiulymas: downgrade metu pirmiau sutvarkyti/null rows migracijos skriptu.

### INFO

1. Naming conventions atitinka formata:
   - `YYYYMMDD_NNNNNN_<snake_case>.py` yra nuoseklus.
2. Upgrade flow neturi `DROP TABLE` / `DROP COLUMN` destruktyviu veiksmu.
3. State machine doctrine (payments-first) migracijose tiesiogiai nesulauzyta.

## Pritaikytos Pataisos (siame cikle)

- `backend/app/static/calls.html` - PII maskavimas admin lenteleje/kortelese.
- `backend/app/api/v1/deploy.py` - token compare hardening + output leak mazinimas + 404 on invalid token.
- `backend/app/services/notification_outbox_channels.py` - WhatsApp numerio redakcija loguose.
- `backend/app/core/config.py` - praplesti PII redaction keys + CORS wildcard warning + auth config checks.
- `backend/app/api/v1/email_webhook.py` - fail-closed CloudMailin auth + constant-time compare.
- `backend/app/api/v1/projects.py` - redacted audit key alignment + Pydantic payloads.
- `backend/app/schemas/project.py` - naujos request schemos.
- `backend/app/api/v1/client_views.py` - `/client/estimate/rules` auth reikalavimas.
- `backend/app/services/email_auto_reply.py` - redaguotas no-reply email logging.
- Testai:
  - `backend/tests/test_deploy_webhook_security.py` (naujas)
  - `backend/tests/test_notification_outbox_unit.py` (papildytas)
  - `backend/tests/test_email_auto_reply.py` (papildytas redaction testas)

## Validacija

- `ruff check` - PASS (tik paliesti failai)
- `ruff format --check` - PASS
- `python -m compileall` - PASS (paliesti Python failai)
- `pytest` - NEPALEISTA lokaliai (siame hoste nera `pytest` modulio)
