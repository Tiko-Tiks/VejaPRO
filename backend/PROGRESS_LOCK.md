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

- Staging restore drill (requires real `DATABASE_URL_STAGING`).

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

- Enable Fail2ban (SSH brute-force protection).
- Add Nginx rate limits for public endpoints.
- Verify `ADMIN_IP_ALLOWLIST` behavior from allowed vs blocked IP.
- Set UptimeRobot monitor on `https://vejapro.lt/health`.
- Add disk usage watchdog timer (daily).
- Staging restore drill with real `DATABASE_URL_STAGING`.
- Confirm `.env.prod` prod settings:
  - `ALLOW_INSECURE_WEBHOOKS=false`
  - `DOCS_ENABLED=false`, `OPENAPI_ENABLED=false`
  - `SECURITY_HEADERS_ENABLED=true`
- Confirm live keys for Stripe/Twilio/Supabase (if switching from test).
- Run final production smoke test (see `GO_LIVE_PLAN.md`).

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
