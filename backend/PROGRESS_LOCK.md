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
