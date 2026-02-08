# PROGRESS_LOCK (VejaPRO)

This file tracks completed milestones.  
When an item is marked **DONE**, do not modify it.  
Add new lines at the end only.

---

## DONE

- 2026-02-05: Backup job created and verified (`/usr/local/bin/vejapro-backup`, timer `vejapro-backup.timer`).
- 2026-02-05: Backup integrity check OK (`gunzip -t /var/backups/vejapro/vejapro_20260205_103004.sql.gz`).
- 2026-02-05: Health watchdog enabled (`vejapro-healthcheck.timer`) and restart logic fixed.
- 2026-02-05: Admin IP allowlist format fixed (CSV now accepted), service boots OK.
- 2026-02-05: PII redaction setting parse issues fixed (removed invalid env format).

## PENDING

- Schedule Engine: likę TODO punktai — žr. `backend/SCHEDULE_ENGINE_BACKLOG.md`.

---

## DONE (Summary)

- 2026-02-04: Domain `vejapro.lt` routed through Cloudflare Tunnel (CNAME `*.cfargotunnel.com`), HTTPS OK.
- 2026-02-04: Nginx reverse proxy to `127.0.0.1:8000` with real IP handling.
- 2026-02-04: Supabase Postgres connected; Alembic version `20260203_000002`.
- 2026-02-04: Stripe webhook and Twilio webhook end-to-end verified.
- 2026-02-04: Full business flow verified (DRAFT -> PAID -> CERTIFIED -> ACTIVE).
- 2026-02-04: Deployment notes recorded (`DEPLOYMENT_NOTES_2026-02-04.md`).
- 2026-02-05: Go-live plan recorded (`GO_LIVE_PLAN.md`).
- 2026-02-05: Data security plan recorded (`DATA_SECURITY_PLAN.md`).
- 2026-02-05: Auto update timer enabled (`vejapro-update.timer`).
- 2026-02-05: Health watchdog enabled (`vejapro-healthcheck.timer`).
- 2026-02-05: Log rotation for nginx + journald limits configured.
- 2026-02-05: Backup job enabled (`vejapro-backup.timer`).
- 2026-02-05: Admin UI verified with bearer token.

## PENDING (Production Readiness)

- ~~Enable Fail2ban (SSH brute-force protection).~~ DONE 2026-02-05
- ~~Add Nginx rate limits for public endpoints.~~ DONE 2026-02-05
- ~~Verify `ADMIN_IP_ALLOWLIST` behavior from allowed vs blocked IP.~~ DONE 2026-02-05
- ~~Set UptimeRobot monitor on `https://vejapro.lt/health`.~~ DONE 2026-02-05
- ~~Add disk usage watchdog timer (daily).~~ DONE 2026-02-05
- ~~Staging restore drill.~~ DONE 2026-02-06
- ~~Confirm `.env.prod` prod settings.~~ DONE 2026-02-05
- Perjungti Stripe/Twilio į LIVE raktus (šiuo metu TEST režimas).
- Galutinis produkcinis smoke test su **tikrais** raktais (žr. `GO_LIVE_PLAN.md`).

---

## DONE (Append)

- 2026-02-05: Fail2ban enabled (sshd jail active).
- 2026-02-05: Nginx rate limit for public endpoints enabled (webhooks excluded).
- 2026-02-05: Admin IP allowlist check OK (allowed IP returns 401 without token).
- 2026-02-05: UptimeRobot monitor created for `https://vejapro.lt/health`.
- 2026-02-05: Disk usage watchdog enabled (`vejapro-diskcheck.timer`).
- 2026-02-05: Production `.env.prod` flags confirmed (insecure webhooks off, docs off, security headers on).
- 2026-02-05: Live keys not enabled yet (TEST mode retained for Stripe/Twilio).
- 2026-02-05: Final smoke test (TEST mode) passed (project reaches PAID via Stripe DEPOSIT).
- 2026-02-05: Admin UI overview page added (`/admin`) with shared bearer token storage.
- 2026-02-05: Admin Projects UI enhanced (quick create, details modal, status transition).
- 2026-02-05: Admin Projects UI added seed cert photos + certify actions (new admin helper endpoint).
- 2026-02-05: Admin UI token handling hardened (auto-trim and strip Bearer prefix).
- 2026-02-05: Admin UI token handling hardened (remove whitespace/newlines in JWT).
- 2026-02-05: Admin token generator endpoint added (`/api/v1/admin/token`) + UI button on admin pages.
- 2026-02-05: Full flow verified end-to-end including SMS confirmation to `ACTIVE` (project `fa0b67b2-...`).
- 2026-02-05: Public landing page added (`/` → `static/landing.html`).
- 2026-02-05: Public landing page refreshed (more visuals) and VejaPRO logo wired in header (/static/assets/vejapro-logo.png).
- 2026-02-05: Admin Projects UI auto-refreshes token on 401 and shows clearer API errors.
- 2026-02-05: FINAL payment + SMS confirmation flow verified (project reached ACTIVE).
- 2026-02-05: Call assistant + calendar backend added (tables `call_requests`, `appointments`, migration `20260205_000003`).
- 2026-02-05: Admin Calls and Calendar UI pages added (`/admin/calls`, `/admin/calendar`), nav updated across admin pages.
- 2026-02-06: Documentation updated (deploy/rollback, staging tests, troubleshooting) in SYSTEM_CONTEXT.md / PROJECT_CONTEXT.md / .windsurfrules.
- 2026-02-06: Staging infra wired: Supabase staging DB migrated, `vejapro-staging` service (port 8001), Nginx + Cloudflared `staging.vejapro.lt`, staging token endpoint enabled.
- 2026-02-06: Call Assistant enabled in staging (`.env.staging`: `ENABLE_CALL_ASSISTANT=true`, `ENABLE_CALENDAR=true`).
- 2026-02-06: Landing page call request form added (`landing.html` with POST to `/api/v1/call-requests`).
- 2026-02-06: Call Assistant test plan created (`CALL_ASSISTANT_TEST_PLAN.md`).
- 2026-02-06: Migration added/applied for `evidences.created_at` (`20260206_000004`).
- 2026-02-06: Staging smoke test OK (DRAFT -> PAID -> SCHEDULED -> PENDING_EXPERT -> CERTIFIED -> ACTIVE). Stripe/Twilio simulated in staging.
- 2026-02-06: Supabase advisor security issues fixed (RLS enabled on all tables, migrations `20260206_000005`, `20260206_000006`).
- 2026-02-06: Foreign key indexes added for performance (margins.created_by, projects.assigned_contractor_id, projects.assigned_expert_id).
- 2026-02-06: Staging restore drill completed (prod public dump -> staging public schema wipe/restore, alembic upgraded).
- 2026-02-06: Final production smoke test (TEST mode) OK (project `7e05cd54-379b-4106-9abe-ba5a9428ea3a` -> ACTIVE; Stripe webhook simulated with signature, SMS confirmation simulated).
- 2026-02-06: Client portal UI added (`/client`) with read-only project view and marketing consent toggle.
- 2026-02-06: Admin endpoint added to issue client JWT (`/api/v1/admin/projects/{project_id}/client-token`).
- 2026-02-06: Admin Projects UI action added to generate client token (modal with copy + portal link).
- 2026-02-06: Client projects list endpoint added (`/api/v1/client/projects`).
- 2026-02-06: Client portal updated to list client projects (uses `/api/v1/client/projects`).
- 2026-02-06: Landing page links to `/client`; client portal auto-loads project list when token present.
- 2026-02-06: Call Assistant flow verified end-to-end (landing form -> admin calls -> calendar appointment -> audit logs).
- 2026-02-06: Date/time pickers upgraded to LT locale, 24h format, Monday week start (flatpickr, self-hosted).
- 2026-02-06: Server timezone set to Europe/Vilnius (staging VM).
- 2026-02-06: Landing page design improved (form styling, date picker, hero gradient, feature cards with hover effects).
- 2026-02-06: Public gallery UI created (`/gallery`) with before/after slider, filters, infinite scroll, lightbox modal.
- 2026-02-06: Gallery feature documented (`GALLERY_DOCUMENTATION.md`) with API specs, usage, admin workflow, troubleshooting.
- 2026-02-06: Contractor portal created (`/contractor`) with JWT auth, project list, filters, statistics dashboard.
- 2026-02-06: Expert portal created (`/expert`) with JWT auth, certification workflow, checklist, evidence grid.
- 2026-02-06: Contractor/expert API endpoints added (`/api/v1/contractor/projects`, `/api/v1/expert/projects`).
- 2026-02-06: Token generation endpoints added for contractor/expert (`/api/v1/admin/users/{id}/contractor-token`, `/api/v1/admin/users/{id}/expert-token`).
- 2026-02-06: Contractor/expert portals documented (`CONTRACTOR_EXPERT_PORTALS.md`) with API specs, workflows, testing guide.
- 2026-02-06: BUG FIX: AuditLog metadata column always NULL — renamed `meta` to `audit_meta` attribute (`app/models/project.py`, `app/api/v1/projects.py`). DB column remains `metadata`.
- 2026-02-06: SECURITY FIX: Actor override in transition-status restricted to ADMIN only (`app/api/v1/projects.py`).
- 2026-02-06: SECURITY FIX: HTML injection in certificate PDF — added html.escape() (`app/utils/pdf_gen.py`).
- 2026-02-06: SECURITY FIX: X-Forwarded-For spoofing — now uses X-Real-IP first, then rightmost XFF entry (`app/utils/rate_limit.py`).
- 2026-02-06: SECURITY FIX: Rate limit added to public `/api/v1/call-requests` (10/min/IP) (`app/api/v1/assistant.py`).
- 2026-02-06: FIX: SMS service error handling — TwilioRestException catch, logging, returns message SID (`app/services/sms_service.py`).
- 2026-02-06: FIX: Silent exception swallowing in audit alert tracker — now logs errors (`app/services/transition_service.py`).
- 2026-02-06: FIX: Memory leak in rate limiter and alert tracker — stale bucket pruning added (`app/utils/rate_limit.py`, `app/utils/alerting.py`).
- 2026-02-06: DOC: `SYSTEM_CONTEXT.md` papildytas — pridėta Windows dev aplinka, Ubuntu server aplinka, SSH prisijungimo instrukcijos, vienos eilutės deploy/test komandos.
- 2026-02-06: ui: cleanup — pašalinta hero stock nuotrauka ir placeholder statistika iš landing page.
- 2026-02-06: ui: Profesionalus logo su lapo ikona ir stilizuota tipografija.
- 2026-02-06: ui: Landing page dizaino perdirbimas — hero, ikonos, timeline, animacijos.
- 2026-02-06: ui: Landing page turinio atnaujinimas su tikrais kontaktais (tel, el. paštas, darbo valandos).
- 2026-02-07: ui: Landing page dizaino pagerinimas — spalvų schema, šešėliai, kortelių hover efektai, sekcijų atskyrimai.
- 2026-02-07: feat: RBAC hardening — griežtesni rolių patikrinimai, portalų UI atnaujinimas, saugumo peržiūra.
- 2026-02-07: fix: Disable page cache ir normalize Lithuanian UI copy.
- 2026-02-07: fix: Marketing flag tests for RBAC assignments.
- 2026-02-07: i18n: Pilnas web sąsajos vertimas į lietuvių kalbą — 9 HTML failai (landing, admin, projects, client, audit, calls, calendar, margins, contractor). Navigacija, formos, modalai, JS pranešimai, title.
- 2026-02-07: DOC: Schedule Engine V1 spec added (`SCHEDULE_ENGINE_V1_SPEC.md`) - deterministic planning, replanning, alerts, and chat/call conflict handling.
- 2026-02-07: DOC: Schedule Engine V1 papildytas - ivestas misrus atsiskaitymas (Stripe + grynieji), cash audit ivykiai, cash endpointai, ir ACTIVE kontrolinis saugiklis cash galutiniam mokejimui.
- 2026-02-07: Schedule Engine Phase 0 implementation started (config keys, DB models/migration scaffold, preview+confirm API with audit and row_version safeguards).
- 2026-02-07: Schedule Engine Phase 0 įgyvendinta: `RESCHEDULE` preview+confirm API su HMAC hash, row_version ir lock_level saugikliais, audit įvykiais (`SCHEDULE_RESCHEDULED`, `APPOINTMENT_CANCELLED`, `APPOINTMENT_CONFIRMED`).
- 2026-02-07: Schedule Engine Phase 2 įgyvendinta: `HELD` rezervacijos (Hold API) su `conversation_locks`, patvirtinimu ir expire mechanizmu.
- 2026-02-07: Schedule Engine Phase 3 įgyvendinta: `Daily batch approve` API (`/api/v1/admin/schedule/daily-approve`) su `lock_level=2` ir audit (`DAILY_BATCH_APPROVED`, `APPOINTMENT_LOCK_LEVEL_CHANGED`).
- 2026-02-07: Admin kalendoriaus UI atnaujintas: pridėtas „Planavimo įrankiai“ blokas su „Patvirtinti dieną“ veiksmu (resource_id neprivalomas; jei nepateiktas audit'e fiksuojama `resource_id=ALL`).
- 2026-02-07: Payments-first doktrina įvesta: pridėti feature flag'ai `ENABLE_MANUAL_PAYMENTS`, `ENABLE_STRIPE`, `ENABLE_TWILIO`; Stripe padarytas optional; manual mokėjimai default.
- 2026-02-07: Manual mokėjimų faktai: naujas endpoint `POST /api/v1/projects/{project_id}/payments/manual` su idempotencija (provider_event_id), audit `PAYMENT_RECORDED_MANUAL`, ir FINAL->SMS inicijavimu (jei projektas CERTIFIED).
- 2026-02-07: Statusų perėjimo saugiklis: `DRAFT -> PAID` leidžiamas tik jei yra `payments` DEPOSIT faktas (manual arba stripe), su audit per `transition-status` (statusų aibė nekeičiama).
- 2026-02-07: Dokumentacija atnaujinta: `VEJAPRO_KONSTITUCIJA_V1.4.md`, `VEJAPRO_TECHNINĖ_DOKUMENTACIJA_V1.5.1.md` (patch).
- 2026-02-07: BUG FIX: Admin `projects.html` sertifikavimo checklist sutvarkytas (sutampa su eksperto portalu: ground/seed/edges/robot/perimeter/cleanliness).
- 2026-02-07: BUG FIX: Rangovo portale pašalinta neegzistuojanti `/projects/{id}` nuoroda, vietoje to pridėta „Atidaryti sertifikatą“ (tik CERTIFIED/ACTIVE).
- 2026-02-07: i18n: Išversti likę angliški klaidų pranešimai (sertifikavimo nuotraukos, sertifikato sąlyga).
- 2026-02-07: fix: GitHub Actions CI workflow YAML sintaksė sutvarkyta (indentacija) (`.github/workflows/ci.yml`).
- 2026-02-07: chore: Pridėtos agentų taisyklės Cursor/Windsurf naudojimui (`.cursorrules`, `.windsurfrules`).
- 2026-02-07: Mobile: Responsive dizainas pridėtas visiems 11 HTML failų — media queries (768px, 480px), touch targets (min 44px), lentelių→kortelių transformacija mobiliuose.
- 2026-02-07: Mobile: data-label atributai pridėti audit.html, projects.html, calendar.html, calls.html, margins.html lentelėms.
- 2026-02-07: CI/CD: GitHub Actions CI pataisytas — pridėtas ruff lint job, trūkstami feature flags (ENABLE_CALL_ASSISTANT, ENABLE_CALENDAR, ENABLE_SCHEDULE_ENGINE, ADMIN_IP_ALLOWLIST), pytest -v --tb=short.
- 2026-02-07: CI/CD: GitHub Actions Deploy pataisytas — atkomentuotas systemctl restart, teisingi servisų pavadinimai (vejapro.service, vejapro-staging.service), deploy target pasirinkimas (production/staging/both), health checks, appleboy/ssh-action v1.2.0.
- 2026-02-07: Config: ruff.toml pridėtas Python lintingui (E, W, F, I, B, UP taisyklės).
- 2026-02-07: SECURITY: XSS pataisytas contractor.html (onclick→addEventListener, UUID sanitizavimas) ir margins.html (escape funkcija naudotojo duomenims).
- 2026-02-07: FIX: AppointmentStatus enum — pašalintas CANCELED dublikatas, paliktas tik CANCELLED. calendar.html atitinkamai atnaujintas.
- 2026-02-07: SECURITY: Cache headers — /contractor ir /expert dabar naudoja _client_headers() (no-store) vietoj _public_headers().
- 2026-02-07: CLEANUP: project_service.py pašalintas (nenaudojamas dublikatas transition_service.py ALLOWED_TRANSITIONS).
- 2026-02-07: i18n: ~70 angliškų API klaidų pranešimų išversta į lietuvių kalbą (projects.py, assistant.py, schedule.py, transition_service.py).
- 2026-02-07: i18n: Frontend angliški pranešimai išversti projects.html ("Ready"→"Paruošta", "Failed"→"Nepavyko", "Create failed"→"Sukūrimas nepavyko", "Transition failed"→"Perėjimas nepavyko").
- 2026-02-07: Twilio Voice webhook MVP pridetas (/api/v1/webhook/twilio/voice) - pasiulo laika su HELD rezervacija ir patvirtina/atsaukia pagal 1/2 arba 'tinka/netinka'.
- 2026-02-07: Chat webhook MVP pridetas (/api/v1/webhook/chat/events) - minimalus pasiulymo ir HELD patvirtinimo/atsaukimo srautas, vienas tiesos saltinis backend'e.
- 2026-02-07: Hold expiry worker pridetas (in-process) - periodiskai atstato pasibaigusias HELD rezervacijas i CANCELLED (HOLD_EXPIRED) ir isvalo conversation_locks.
- 2026-02-07: fix: GitHub Actions workflow'ai normalizuoti (quoted on, branches list) (.github/workflows/ci.yml, .github/workflows/deploy.yml).
- 2026-02-07: feat: Notification outbox pridetas: 
otification_outbox lentele + in-process worker + RESCHEDULE confirm SMS enqueue (idempotency per dedupe_key).
- 2026-02-07: ui: Admin kalendorius papildytas RESCHEDULE (preview/confirm) srautu (ackend/app/static/calendar.html) + preview atsakyme grazinami expected_versions.
- 2026-02-07: UI: Pridetas logotipas (static/logo.png) i landing ir portalus (admin/audit/calendar/calls/margins/projects, client/contractor/expert/gallery).
- 2026-02-07: Security: Ijungtas API rate limit pagal nutylejima (RATE_LIMIT_API_ENABLED), sustiprinta JWT validacija (aud per SUPABASE_JWT_AUDIENCE), vidiniai JWT papildyti aud, SMS loguose slepiamas telefono numeris (PII redaction).
- 2026-02-07: Security: Pridetas klaidu detaliu slepimas per EXPOSE_ERROR_DETAILS (5xx), patobulintas rate limiter valymas (periodinis stale bucket prune), sutvarkyti 5xx pranesimai (LT), atnaujinta technine dok. V1.5.1.
- 2026-02-07: DOC: Pridetas pilnas API endpointu katalogas (`backend/API_ENDPOINTS_CATALOG_V1.52.md`) + nuoroda is Tech Docs V1.5; assistant audite `actor_type` suvienodintas (PUBLIC->CLIENT) ir admin assistant/calendar endpointai suvienodinti pagal feature flag (404 kai isjungta).
- 2026-02-07: CI: Ruff lint pataisytas — pašalintas continue-on-error, pridėtas needs: lint, papildyti CI env (ENABLE_NOTIFICATION_OUTBOX, ENABLE_VISION_AI, ADMIN_TOKEN_ENDPOINT_ENABLED).
- 2026-02-07: CI: Deploy pataisytas — input injection apsauga (envs: DEPLOY_TARGET), command_timeout: 120s, health check sleep 5s.
- 2026-02-07: LINT: Import sorting (I001) sutvarkytas 18 failų. ruff.toml papildytas: UP045/UP017/UP012 ignore, known-first-party=["app"].
- 2026-02-07: DOC: Cursor rules ir SYSTEM_CONTEXT/README atnaujinti su ruff import tvarka ir CI/CD taisyklėmis (kad klaidos nesikartotų).
- 2026-02-07: fix: SQLAlchemy atomicity bug — chat_webhook.py ir twilio_voice.py: pašalintas per anksti `db.commit()` po call_request sukūrimo, preferred_time dabar toje pačioje transakcijoje kaip ir appointment/lock. IntegrityError handleriuose pridėtas call_request atkūrimas po rollback.
- 2026-02-07: fix: W292 (no newline at end of file) — chat_webhook.py. Pridėtas trūkstamas `\n` failo gale.
- 2026-02-07: DOC: Cursor rules atnaujinti su prevencija — pridėtos W292 (newline), SQLAlchemy sesijos ekspiracija, pre-push checklist (`ruff check` + `ruff format --check`).
- 2026-02-08: DB schema higiena: migracija `20260208_000011_schema_hygiene_constraints.py` pridėta (Postgres) — `appointments` `chk_appointment_time` (`ends_at > starts_at`), `created_at`/`timestamp` backfill + `SET NOT NULL`, `evidences.uploaded_by` FK į `users.id` (`ON DELETE SET NULL`) + duomenų cleanup.
- 2026-02-08: Security/RLS: migracija `20260208_000012_enable_rls_for_new_tables.py` — įjungtas RLS ir `service_role_all` policy naujoms lentelėms (`conversation_locks`, `project_scheduling`, `schedule_previews`, `notification_outbox`).
- 2026-02-08: UI: Admin kalendorius — RESCHEDULE UX patobulinimai: greiti reason mygtukai (LT), preview meta/summary (CANCEL/CREATE/travel), preview TTL countdown, focus į comment kai reason=OTHER.
- 2026-02-08: Security: papildomas escaping admin lentelėse (ypač datų laukams), kad nebūtų XSS per `innerHTML` renderinimą.
- 2026-02-08: Voice/Chat stabilizacija: webhook'ai (`/api/v1/webhook/twilio/voice`, `/api/v1/webhook/chat/events`) nebekuria dublio `conversation_locks` retry atveju — jei aktyvus HELD jau yra, per-pasiulo ta pati laika; konfliktu atveju bando pasiulyti kita deterministini slota (ribotas retry).
- 2026-02-08: Web chat widget MVP: pridetas public testavimo puslapis `/chat` (`backend/app/static/chat.html`) su pokalbio state atvaizdavimu ir mygtukais "Tinka"/"Netinka".
- 2026-02-08: Voice/Chat: papildoma konkurencingumo taisykle per klienta (tel. numeri) — tas pats `from_phone` vienu metu turi tik viena aktyvu `HELD`; naujas pokalbis/CallSid perima esama `HELD` ir perraso `conversation_locks`.
- 2026-02-08: Voice/Chat: papildomas overlap re-check pries `HELD` insert (CI/SQLite stabilumui) + testai konfliktu scenarijui (pasiulo kita slota).

- 2026-02-08: Testing infra: backend testai perkelti ÄÆ in-process `httpx.ASGITransport` (CI nebestartuoja uvicorn; `USE_LIVE_SERVER=true` + `BASE_URL=...` lieka opt-in).
- 2026-02-08: CI: pytest junit ataskaita publikuojama kaip GitHub Check (dorny/test-reporter) greitesniam diagnostikos matymui.
- 2026-02-08: FIX: Schedule Engine (SQLite/CI) ? SELECT ... FOR UPDATE nebesinaudojamas SQLite dialekte (guard per `db.bind.dialect.name`), kad testai b?t? suderinami su Postgres ir nel??t? CI.
- 2026-02-08: TEST: conftest autouse fixture ? `get_settings.cache_clear()` prie?/po kiekvieno testo, kad `SUPABASE_JWT_SECRET`/audience monkeypatch nepasilikt? cache ir nelau?yt? kit? test? (401 Netinkamas ?etonas).
- 2026-02-08: Voice (Twilio): papildoma CallSid idempotency apsauga ? jei HOLD k?rimas meta IntegrityError, per-checkinamas esamas `conversation_lock` ir re-promptinamas tas pats HELD (ne kuriamas naujas). Taip pat `SELECT ... FOR UPDATE` guard SQLite dialekte.
- 2026-02-08: UI: Admin kalendorius — RESCHEDULE confirm klaidu UX: `resp.ok` tikrinimas, 409/410 konfliktu atveju auto-refresh (1x) per preview, po to prašo atlikti Preview dar kartą.
- 2026-02-08: Chat webhook (`/api/v1/webhook/chat/events`): SQLite-saugus row locking (be `SELECT ... FOR UPDATE` SQLite dialekte) + formatavimas suderintas su Ruff.
- 2026-02-08: feat: Nuotraukų optimizavimo pipeline — automatinis thumbnail/medium WebP generavimas per Pillow, responsive gallery su blur-up placeholder ir srcset.
  - Naujas modulis: `app/core/image_processing.py` (Pillow: EXIF transpose, thumbnail 400x300 WebP q80, medium 1200px WebP q85, >2MB re-compress JPEG q90).
  - Naujas modulis: `app/core/storage.py` papildytas `upload_image_variants()` (3 failai: originalas + `_thumb.webp` + `_md.webp` į Supabase Storage).
  - DB migracija: `20260208_000013_add_evidence_image_variants.py` — `thumbnail_url TEXT`, `medium_url TEXT` ant `evidences` lentelės.
  - Modelis: `Evidence` — pridėti `thumbnail_url`, `medium_url` stulpeliai (nullable, backward-compatible).
  - Schemos: `EvidenceOut`, `GalleryItem`, `UploadEvidenceResponse` — pridėti `thumbnail_url`, `medium_url` laukai.
  - API: `upload_evidence()` naudoja `process_image()` + `upload_image_variants()` vietoj senojo `upload_evidence_file()`.
  - API: `get_gallery()` grąžina `thumbnail_url` galerijos kortelėse.
  - Frontend: `gallery.html` — thumbnail grid, blur-up placeholder, `srcset`/`sizes` responsive images.
  - Frontend: `client.html`, `expert.html` — evidence grid naudoja `thumbnail_url`, paspaudimas atidaro pilną vaizdą.
  - Dependency: `Pillow==11.*` pridėta į `requirements.txt`.
  - Testai: `test_marketing_flags.py`, `test_rbac_hardening.py` — mock'ai atnaujinti `upload_image_variants` su `_StubUploaded`.
  - CI fix: `UP037` (quoted type annotation su `from __future__ import annotations`), ruff format (trailing blank line).
- 2026-02-08: DOC: GALLERY_DOCUMENTATION.md atnaujinta su image optimization pipeline (schema, performance, changelog).
- 2026-02-08: CI: Stabilizacijos patikra — `ruff check` PASS, `ruff format --check` PASS (65 failai), `pytest` PASS (73 testai, 0 failures, 13.74s). Serveris (Ubuntu) atnaujintas iki `main` HEAD.
- 2026-02-08: DOC: Dokumentacijos auditas ir atnaujinimas — PROGRESS_LOCK, GO_LIVE_PLAN, PROJECT_CONTEXT, SYSTEM_CONTEXT, README sinchronizuoti su esama kodo busena.
- 2026-02-08: feat: Finance Module Phase 2 — dokumentų įkėlimas, AI ekstrakcija, Quick Payment.
  - `app/api/v1/finance.py`: Bug fix (`settings` kintamasis vietoj `get_settings()`), pašalinti nenaudojami importai (`Body`, `SmsConfirmation`, `PaymentType`), ruff format.
  - `app/schemas/finance.py`: `QuickPaymentRequest` + `QuickPaymentResponse` schemos (iš praeitosios sesijos).
  - `app/static/finance.html`: Naujas Admin Finance UI su 3 tab'ais (Knygos įrašai, Dokumentai, Tiekėjų taisyklės) + suvestinė.
  - `app/main.py`: `/admin/finance` route pridėtas.
  - `tests/test_finance_ledger.py`: 15 naujų testų:
    * `test_upload_document` — dokumento įkėlimas su SHA-256 hash.
    * `test_upload_duplicate_document_rejected` — 409 kai SHA sutampa (dedup).
    * `test_upload_empty_file_rejected` — 400 tuščiam failui.
    * `test_list_documents` — dokumentų sąrašas su paginacija.
    * `test_documents_gated_by_ai_ingest_flag` — 404 kai `ENABLE_FINANCE_AI_INGEST=false`.
    * `test_extract_document_with_vendor_match` — auto-match "shell" → FUEL kategorija.
    * `test_extract_document_rules_disabled` — stub kai `ENABLE_FINANCE_AUTO_RULES=false`.
    * `test_post_document_to_ledger` — EXTRACTED → POSTED statusas.
    * `test_post_already_posted_document_rejected` — 400 double-post atveju.
    * `test_quick_payment_deposit` — DRAFT + DEPOSIT mokėjimas.
    * `test_quick_payment_idempotency` — tas pats `provider_event_id` (idempotencija).
    * `test_quick_payment_wrong_status` — PAID + DEPOSIT = 400.
    * `test_quick_payment_invalid_type` — "INVALID" = 400.
    * `test_quick_payment_nonexistent_project` — 404.
    * `test_admin_finance_page_returns_html` — UI route testas.