# Go-Live Plan (VejaPRO)

Date: 2026-02-05  
Scope: production readiness, rollout, monitoring, rollback

---

## 1) Pre-Launch Checklist (Must-Do)

### Infrastructure
- [ ] `vejapro.lt` and `www` resolve to Cloudflare Tunnel (CNAME `*.cfargotunnel.com`).
- [ ] `https://vejapro.lt/health` returns 200.
- [ ] Systemd services running: `vejapro`, `cloudflared`, `nginx`.
- [ ] `vejapro-update.timer` enabled (auto pull + restart).

### Secrets / Env (Ubuntu)
- [ ] `.env.prod` contains:
  - `DATABASE_URL`
  - `SUPABASE_JWT_SECRET`
  - `STRIPE_SECRET_KEY`
  - `STRIPE_WEBHOOK_SECRET`
  - `TWILIO_ACCOUNT_SID`
  - `TWILIO_AUTH_TOKEN`
  - `TWILIO_FROM_NUMBER`
  - `TWILIO_WEBHOOK_URL=https://vejapro.lt/api/v1/webhook/twilio`
- [ ] `ALLOW_INSECURE_WEBHOOKS=false` (prod)
- [ ] `DOCS_ENABLED=false` and `OPENAPI_ENABLED=false` (prod)
- [ ] `SECURITY_HEADERS_ENABLED=true`
- [ ] Optional: `ADMIN_IP_ALLOWLIST=...`
- [ ] Optional: `RATE_LIMIT_API_ENABLED=true`

### Data Security (PII / Retention)
- [ ] `PII_REDACTION_ENABLED=true`
- [ ] Review `PII_REDACTION_FIELDS` (default: phone,email,address,ssn,tax_id,passport,national_id,id_number)
- [ ] Set `AUDIT_LOG_RETENTION_DAYS` (default 90)
- [ ] Confirm manual purge process (see `DATA_SECURITY_PLAN.md`)

### Webhooks
- [ ] Stripe webhook: `https://vejapro.lt/api/v1/webhook/stripe`
  - Events: `payment_intent.succeeded`
- [ ] Twilio webhook: `https://vejapro.lt/api/v1/webhook/twilio` (HTTP POST)

### Database
- [ ] Alembic version is `20260206_000006` (latest)
- [ ] Supabase backups enabled (auto or scheduled)
- [ ] Test restore steps known (see Section 5)

### Smoke Tests (prod)
- [ ] Create project → status `DRAFT`
- [ ] Stripe DEPOSIT → status `PAID` (audit log `SYSTEM_STRIPE`)
- [ ] Add 3 evidences for `EXPERT_CERTIFICATION`
- [ ] Certify → status `CERTIFIED`
- [ ] Stripe FINAL → SMS sent
- [ ] Reply `TAIP <TOKEN>` → status `ACTIVE`

---

## 2) Launch Day (Runbook)

1. Freeze code changes (no new commits during launch window).
2. Pull latest on server:
   ```bash
   cd ~/VejaPRO
   git pull --rebase origin main
   sudo systemctl restart vejapro
   ```
3. Verify:
   ```bash
   curl -I https://vejapro.lt/health
   ```
4. Run final smoke test.
5. Monitor audit logs in Admin UI.

---

## 3) Post-Launch (First 24h)

- Monitor uptime (UptimeRobot).
- Check:
  ```bash
  journalctl -u vejapro -n 200 --no-pager
  journalctl -u cloudflared -n 50 --no-pager
  ```
- Validate:
  - Stripe webhook events hitting `/webhook/stripe`
  - Twilio webhook events hitting `/webhook/twilio`
- Ensure no 5xx spikes in Nginx logs:
  ```bash
  tail -n 200 /var/log/nginx/error.log
  ```

---

## 4) Rollback Plan

If a release breaks:

```bash
cd ~/VejaPRO
git fetch origin
git reset --hard <GOOD_COMMIT_HASH>
sudo systemctl restart vejapro
```

Note: Use only known “good” commits. Track them in release notes.

---

## 5) Backups (Supabase)

Recommended:
- Enable daily scheduled backups in Supabase.
- Keep at least 7–14 days of retention.

Manual export (example):
```bash
pg_dump "$DATABASE_URL" > /tmp/vejapro_backup.sql
```

Restore test (staging or temporary DB):
```bash
psql "$DATABASE_URL" < /tmp/vejapro_backup.sql
```

---

## 6) Monitoring & Alerts

Enabled:
- UptimeRobot on `https://vejapro.lt/health`
- systemd auto-update timer
- journald retention limits
- nginx logrotate

Optional:
- Email/SMS alerts from UptimeRobot
- Disk usage alert when >85%

---

## 7) Admin UI Access (Secure)

Admin UI endpoints:
- `/admin` — apžvalga
- `/admin/projects` — projektų valdymas
- `/admin/calls` — skambučių užklausos
- `/admin/calendar` — kalendorius
- `/admin/audit` — audito žurnalas
- `/admin/margins` — maržų taisyklės

Public portals:
- `/` — viešas pradinis puslapis (lietuvių k.)
- `/gallery` — viešoji galerija
- `/client` — klientų portalas (JWT)
- `/contractor` — rangovo portalas (JWT)
- `/expert` — eksperto portalas (JWT)

Access requires:
- Admin puslapiai: `Authorization: Bearer <JWT>` + optional `ADMIN_IP_ALLOWLIST`
- Portalai: `Authorization: Bearer <JWT>` (atitinkamos rolės)
- Visa UI sąsaja lietuvių kalba (lang="lt")

---

## 8) Ownership & Responsibility

- Code owner: GitHub main branch
- Infra owner: Ubuntu VM (administrator)
- DB owner: Supabase project
- Payments: Stripe
- SMS: Twilio
