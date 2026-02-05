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
