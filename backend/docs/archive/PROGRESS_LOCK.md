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

---

## 2026-02-08: AI Modulių Testavimo Sistema V5 (Intent Scope)

**Architektūra:**
- **app/services/ai/common/** — bendra sluoksnis:
  - **providers/** — `BaseProvider` + `ProviderResult` kontraktai, `get_provider()` factory su soft-fallback į mock.
    - `mock.py` — deterministinis mock provider (visada grąžina `{"intent": "mock", "confidence": 1.0}`).
    - `claude.py`, `groq.py`, `openai.py` — tikri API provider'iai (httpx async).
  - `router.py` — resolve override > ENV > prod-fallback grandinė + allowlist validacija.
  - `json_tools.py` — sliding brace-balanced JSON ekstrakcija (robust ištraukimas iš LLM atsakymų).
  - `audit.py` — `AI_RUN` audit įrašai su SHA-256 hash'ais (raw tik `AI_DEBUG_STORE_RAW=true`).
- **app/services/ai/intent/** — intent scope:
  - `contracts.py` — `AIIntentResult` + `VALID_INTENTS` validacija (8 intent'ai: schedule_visit, request_quote, check_status, complaint, general_inquiry, cancel, reschedule, mock).
  - `service.py` — `parse_intent()` su budget-based retry (`AI_INTENT_TIMEOUT_SECONDS=1.2`, `AI_INTENT_BUDGET_SECONDS=2.0`).
- **app/services/ai/vision/** + **finance_extract/** — placeholder'iai (Phase 2).

**ENV konfigūracija (config.py):**
- `ENABLE_AI_INTENT`, `ENABLE_AI_VISION`, `ENABLE_AI_FINANCE_EXTRACT`, `ENABLE_AI_OVERRIDES`, `AI_DEBUG_STORE_RAW`.
- `AI_INTENT_PROVIDER`, `AI_INTENT_MODEL`, `AI_INTENT_TIMEOUT_SECONDS`, `AI_INTENT_BUDGET_SECONDS`, `AI_INTENT_MAX_RETRIES`.
- `AI_TEMPERATURE`, `AI_MAX_TOKENS`, `AI_TIMEOUT_SECONDS`.
- `AI_ALLOWED_PROVIDERS` (CSV, force "mock"), `AI_ALLOWED_MODELS_GROQ/CLAUDE/OPENAI` (CSV).
- `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`.

**API endpoint:**
- `POST /api/v1/admin/ai/parse-intent` (ADMIN only) — klasifikuoja skambučio tekstą.
- Request: `{"text": "...", "override_provider": "groq", "override_model": "llama-3.1-70b"}`.
- Response: `{"intent": "schedule_visit", "confidence": 0.9, "params": {...}, "provider": "groq", "model": "...", "attempts": 1, "latency_ms": 850}`.

**UI (calendar.html):**
- Nauja "AI Įrankiai" sekcija su parse-intent testeriu (textarea + provider/model override).

**Testai (test_ai_module.py — 32 tests):**
1. **JsonToolsTests (8 tests)** — valid JSON, prefixes, arrays, empty, nested braces, escaped quotes, invalid.
2. **ProviderFactoryTests (5 tests)** — mock always available, fallback on no key/unknown provider.
3. **MockProviderTests (2 tests)** — returns valid JSON, respects model param.
4. **IntentContractTests (6 tests)** — valid intent, unknown rejected, confidence range, all 8 intents.
5. **RouterTests (2 tests)** — default mock, override with `ENABLE_AI_OVERRIDES=true`.
6. **IntentServiceTests (1 test)** — parse_intent with mock provider + audit log.
7. **AIEndpointTests (5 tests)** — success, disabled 404, empty 422, non-admin 403, audit writes.
8. **ConfigAIPropertiesTests (3 tests)** — `ai_allowed_providers` force mock, CSV parsing, `ai_allowed_models` dict.

**Bug fiksas:**
- `AuditLog(metadata=metadata)` → `AuditLog(audit_meta=metadata)` (`transition_service.py` line 89).
- Priežastis: SQLAlchemy column alias clash (`audit_meta` Python attr ↔ `metadata` DB stulpelis).
- Ši latentinė klaida reiškė, kad visi `create_audit_log(metadata=...)` iškvietimai tyliai prarasdavo audit metadata.

**CI (ci.yml):**
- Pridėti `ENABLE_AI_INTENT=true`, `AI_INTENT_PROVIDER=mock`, `AI_ALLOWED_PROVIDERS=mock`.

**Test rezultatai:**
- **32/32** AI tests pass.
- **101 total pass** (100 prieš + 32 nauji - 31 jau skaičiuoti = +1 neto).
- 35 pre-existing SQLite-incompatible failures (test_schedule_engine, test_chat_webhook, etc.) — nepakito.

**Kodo struktūra:**
- **17 naujų failų** (ai/__init__.py, common/{providers, router, json_tools, audit}, intent/{contracts, service}, vision/*, finance_extract/*, api/v1/ai.py, tests/test_ai_module.py).
- **5 modifikuoti failai** (config.py +20 fields, main.py router, calendar.html AI UI, ci.yml env, transition_service.py bug fix).

---

## 2026-02-08: AI Monitoring Dashboard (`/admin/ai`)

**Funkcionalumas:**
- **Metrics Overview** — 4 statistikos kortelės:
  - Viso AI iškvietimų (per pastarąsias 24h).
  - Vidutinė latency (millisec).
  - Vidutinis confidence (0.0–1.0).
  - Viso token'ų (prompt + completion).
- **Provider pasiskirstymas** — bar chart (mock, groq, claude, openai).
- **Intent pasiskirstymas** — grid su intent count'ais (schedule_visit, request_quote, cancel, etc.).
- **Paskutiniai AI iškvietimai** — lentelė su:
  - Timestamp, Scope, Provider, Model, Latency, Tokens, Result (intent + confidence pill).
  - Filtrai: Scope (intent/vision/finance_extract), Provider, Limitas.
  - Cursor-based pagination.

**Duomenų šaltinis:**
- `audit_logs` lentelė: `entity_type="ai"`, `action="AI_RUN"`.
- `metadata`: `latency_ms`, `provider`, `model`, `prompt_tokens`, `completion_tokens`.
- `new_value`: `intent`, `confidence`.

**UI:**
- Naujas route: `GET /admin/ai` → `ai-monitor.html`.
- Pridėtas "AI Monitor" link visų admin puslapių nav (admin.html, audit.html, calendar.html, calls.html, finance.html, margins.html, projects.html).
- Space Grotesk design, mobile responsive, bar chart visualization.
- *Vėliau:* margins.html nav papildytas Finansai + AI Monitor; pašalinti dubliuoti „Finansai“ nuorodų iš finance.html ir calendar.html (8 nuorodų visur).

**Commit:** `ac9fc67` — feat: AI Monitoring Dashboard.

---

## 2026-02-09: V2.2 Unified Client Card (Email Intake)

**Architektūra:**
- `call_requests` tampa Unified Lead Card su JSONB `intake_state` (anketa + workflow + aktyvus pasiūlymas + istorija).
- Email-based intake flow: anketa → auto-prepare → one-click send → accept/reject per email.
- Hold'ai kuriami per `Appointment(status='HELD')` be `ConversationLock` (email neturi pokalbio konteksto).
- Atskiras `EMAIL_HOLD_DURATION_MINUTES` (default 30 min) nuo voice/chat `HOLD_DURATION_MINUTES` (3 min).

**DB migracija (`20260209_000015`):**
- `call_requests`: pridėti `converted_project_id` (FK→projects), `preferred_channel`, `intake_state` (JSONB).
- `evidences`: pridėtas `call_request_id` (FK→call_requests), `project_id` tapo nullable (lead stadijos nuotraukos).
- `sms_confirmations` → `client_confirmations`: pervadinta lentelė, pridėtas `channel` stulpelis.
- Postgres indeksai: `idx_call_requests_email_lower`, `idx_call_requests_intake_state_gin`, `idx_evidences_call_request_id`, `uniq_call_request_confirmed_visit`.

**Nauji failai:**
- `app/services/intake_service.py` — state machine, questionnaire, offer flow, Schedule Engine adapteriai.
- `app/services/notification_outbox_channels.py` — email (.ics), WhatsApp ping (stub), SMS legacy.
- `app/api/v1/intake.py` — admin intake API + public offer response + CERTIFIED→ACTIVE activation.
- `app/schemas/intake.py` — Pydantic schemos intake flow.

**Modifikuoti failai:**
- `app/models/project.py` — CallRequest (3 nauji stulpeliai), Evidence (call_request_id, nullable project_id), SmsConfirmation→ClientConfirmation.
- `app/core/config.py` — SMTP, EMAIL_HOLD, ENABLE_EMAIL_INTAKE, ENABLE_WHATSAPP_PING konfigūracija.
- `app/services/notification_outbox.py` — email + whatsapp_ping kanalų palaikymas outbox worker'yje.
- `app/services/transition_service.py` — SmsConfirmation→ClientConfirmation, SYSTEM_EMAIL aktorius CERTIFIED→ACTIVE.
- `app/schemas/assistant.py` — CallRequestOut papildytas `converted_project_id`, `preferred_channel`, `intake_state`.
- `app/api/v1/assistant.py` — `_call_request_to_out()` atnaujintas.
- `app/api/v1/projects.py`, `app/api/v1/finance.py` — create_sms_confirmation→create_client_confirmation refs.
- `app/main.py` — intake_router registracija.
- `app/static/calls.html` — intake anketa, pasiūlymo valdymas admin UI.

**API endpointai:**
- `GET /api/v1/admin/intake/{id}/state` — intake būsena (ADMIN).
- `PATCH /api/v1/admin/intake/{id}/questionnaire` — anketos atnaujinimas (ADMIN).
- `POST /api/v1/admin/intake/{id}/prepare-offer` — slot'o peržiūra (ADMIN).
- `POST /api/v1/admin/intake/{id}/send-offer` — hold + email siuntimas (ADMIN).
- `GET /api/v1/public/offer/{token}` — viešas pasiūlymo peržiūra.
- `POST /api/v1/public/offer/{token}/respond` — accept/reject.
- `POST /api/v1/public/activations/{token}/confirm` — CERTIFIED→ACTIVE per email.

**ENV kintamieji:**
- `ENABLE_EMAIL_INTAKE` (default=false), `EMAIL_HOLD_DURATION_MINUTES` (default=30), `EMAIL_OFFER_MAX_ATTEMPTS` (default=5).
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_USE_TLS`.
- `ENABLE_WHATSAPP_PING` (default=false).

**RBAC pakeitimai:**
- `CERTIFIED → ACTIVE`: leidžiami aktoriai papildyti — `SYSTEM_TWILIO` (SMS) + `SYSTEM_EMAIL` (email patvirtinimas).
- Naujas aktorių tipas `SYSTEM_EMAIL` naudojamas `/api/v1/public/activations/{token}/confirm` endpoint'e.

**Lentelių schema (po migracijos `20260209_000015`):**
- `call_requests`: `id`, `name`, `phone`, `email`, `preferred_time`, `notes`, `status`, `source`, `created_at`, `updated_at`, **`converted_project_id`** (FK→projects), **`preferred_channel`** (default='email'), **`intake_state`** (JSONB).
- `evidences`: `id`, `project_id` (**nullable**), `file_url`, `file_type`, `label`, `category`, `uploaded_by`, `show_on_web`, `thumbnail_url`, `medium_url`, `created_at`, **`call_request_id`** (FK→call_requests).
- `client_confirmations` (buv. `sms_confirmations`): `id`, `project_id`, `token_hash`, `expires_at`, `confirmed_at`, `confirmed_from_phone`, `status`, `attempts`, `created_at`, **`channel`** (default='sms').

**intake_state JSONB struktūra:**
```json
{
  "questionnaire": {
    "email": {"value": "...", "source": "operator", "confidence": 1.0, "updated_at": "..."},
    "address": {"value": "...", "source": "operator", "confidence": 1.0, "updated_at": "..."},
    "service_type": {"value": "...", "source": "operator", "confidence": 1.0, "updated_at": "..."}
  },
  "workflow": {"phase": "QUESTIONNAIRE_DONE", "row_version": 3, "updated_at": "..."},
  "active_offer": {
    "state": "SENT",
    "kind": "INSPECTION",
    "slot": {"start": "...", "end": "...", "resource_id": "..."},
    "appointment_id": "...",
    "hold_expires_at": "...",
    "token_hash": "...",
    "channel": "email",
    "attempt_no": 1
  },
  "offer_history": [
    {"status": "REJECTED", "reason": "CLIENT_REJECT", "at": "..."}
  ]
}
```

**Workflow fazės:**
- `INTAKE_STARTED` → `QUESTIONNAIRE_DONE` → `OFFER_PREPARED` → `OFFER_SENT` → `INSPECTION_SCHEDULED` (accept) / `OFFER_REJECTED_NO_SLOTS` (reject, nėra laisvų).

**Testai:**
- CI praėjo: `ruff check` PASS, `ruff format --check` PASS, `pytest` PASS.
- 3 papildomi lint fix commit'ai po pagrindinio V2.2 commit'o:
  - `3a1f736` — fix: ruff B904 raise-from + F401 unused imports in intake.py.
  - `151c114` — fix: ruff F841 unused var, F401 unused imports, I001 import sort order.
  - `153453e` — style: ruff format auto-fix (intake, intake_service, transition_service).

---

## 2026-02-09: V2.3 Finansų Modulio Architektūrinė Rekonstrukcija

**P0 (Phase 1+2) — COMPLETE:**
- DB migracija `20260209_000016`: `payments.ai_extracted_data` (JSONB), `UNIQUE(provider, provider_event_id)` indeksas.
- `config.py`: `ENABLE_FINANCE_LEDGER`, `ENABLE_FINANCE_METRICS`, `FINANCE_METRICS_MAX_SSE_CONNECTIONS`, `FINANCE_METRICS_INTERVAL_SECONDS`.
- `transition_service.py`: `is_final_payment_recorded()`, `is_client_confirmed()`, `find_client_confirmation()`, `increment_confirmation_attempt()`.
- `finance.py`: quick-payment `email_queued` (buvo `sms_queued`), row-lock, idempotencija 200/409.
- `projects.py`: FINAL mokėjimas → email confirmation (ne SMS), naujas `POST /public/confirm-payment/{token}` endpointas.
- `schemas/finance.py`: `QuickPaymentResponse.email_queued`.

**P1 (Phase 3) — COMPLETE:**
- SSE metrics endpointas: `GET /admin/finance/metrics` (daily_volume, manual_ratio, avg_attempts, reject_rate, avg_confirm_time_minutes). Max concurrent SSE, be PII.
- AI finance_extract: proposal-only ekstrakcija (`extract_finance_document()`), confidence scoring, niekada auto-confirm.
- `contracts.py`: `AIFinanceExtractResult` su `model_version`, `raw_extraction`.
- 13 naujų testų (`test_v23_finance.py`): idempotencija, email queuing, security 404, SSE metrics, RBAC, email confirmation.
- 4 dokumentacijos atnaujinimai: KONSTITUCIJA V1.4, TECHNINĖ DOK V1.5.1, API CATALOG V1.52, SCHEDULE_ENGINE SPEC.

**Bugs fixed:**
- datetime naive vs aware comparison `confirm-payment` endpointe (SQLite grąžina naive).
- `actor_type="CLIENT"` → `"SYSTEM_EMAIL"` CERTIFIED→ACTIVE tranzicijai.
- Chicken-and-egg: `confirmation.status="CONFIRMED"` + `db.flush()` PRIEŠ `apply_transition()`.

**Testai:** 114 passed (+13 naujų V2.3), 34 failed (pre-existing SUPABASE_JWT_SECRET), 0 regresijų.

---

- 2026-02-10: Fazė C (pagrindas): admin-shared.css, admin-shared.js, admin.html su sidebar, projects.html ir calls.html migruoti į vienodą layout + shared assets.

- 2026-02-11: Client UI V3 (backend-driven): GET /client/dashboard, GET /client/projects/{id}/view, estimate rules/analyze/price/submit, services catalog/request, client action endpoints (pay-deposit, sign-contract, pay-final, confirm-acceptance, order-service), service_requests lentelė (migracija 20260211_000017), client.html hash router (#/, #/projects, #/estimate, #/services, #/help), dokumentacija backend/docs/CLIENT_UI_V3.md.

- 2026-02-11: Dokumentacija atnaujinta po sėkmingo GitHub push (Client UI V3): API_ENDPOINTS_CATALOG.md — 2.8 Client UI V3, VEJAPRO_KONSTITUCIJA_V2.md ir VEJAPRO_TECHNINE_DOKUMENTACIJA_V2.md — nuorodos į CLIENT_UI_V3.md.

- 2026-02-11: Admin UI Operator Workflow (V3.3): sidebar 240px/#1a1a2e, token collapsible apačioje, GET /admin/dashboard (hero, triage, ai_summary), GET /admin/dashboard/sse, triage cards horizontal scroll, filter chips customers.html, Summary tab pirmas customer-profile.html, urgency rows (high/medium/low), startDashboardSSE, quickAction helper, ENABLE_AI_SUMMARY config.

- 2026-02-11: Dokumentacija atnaujinta: README.md, ADMIN_UI_V3.md (Faze D, V3.3), API_ENDPOINTS_CATALOG.md (2.1.1 Admin Dashboard, feature flags), VEJAPRO_TECHNINE_DOKUMENTACIJA_V2.md (admin_dashboard.py), .env.example (ENABLE_AI_SUMMARY, DASHBOARD_SSE_MAX_CONNECTIONS).
