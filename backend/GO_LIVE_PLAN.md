# Go-Live Plan (VejaPRO)

Date: 2026-02-05  
Scope: production readiness, rollout, monitoring, rollback

---

## 1) Pre-Launch Checklist (Must-Do)

### Infrastructure
- [x] `vejapro.lt` and `www` resolve to Cloudflare Tunnel (CNAME `*.cfargotunnel.com`).
- [x] `https://vejapro.lt/health` returns 200.
- [x] Systemd services running: `vejapro`, `cloudflared`, `nginx`.
- [x] `vejapro-update.timer` enabled (auto pull + restart).

### Secrets / Env (Ubuntu)
- [x] `.env.prod` contains:
  - `DATABASE_URL`
  - `SUPABASE_JWT_SECRET`
  - `STRIPE_SECRET_KEY`
  - `STRIPE_WEBHOOK_SECRET`
  - `TWILIO_ACCOUNT_SID`
  - `TWILIO_AUTH_TOKEN`
  - `TWILIO_FROM_NUMBER`
  - `TWILIO_WEBHOOK_URL=https://vejapro.lt/api/v1/webhook/twilio` (SMS)
  - `TWILIO_VOICE_WEBHOOK_URL=https://vejapro.lt/api/v1/webhook/twilio/voice` (Voice)
- [x] `ALLOW_INSECURE_WEBHOOKS=false` (prod)
- [x] `DOCS_ENABLED=false` and `OPENAPI_ENABLED=false` (prod)
- [x] `SECURITY_HEADERS_ENABLED=true`
- [x] Optional: `ADMIN_IP_ALLOWLIST=...`
- [x] Optional: `RATE_LIMIT_API_ENABLED=true`
- [x] V2.3 Finance: `ENABLE_FINANCE_LEDGER`, `ENABLE_FINANCE_METRICS`
- [x] V2.2 Email: `ENABLE_EMAIL_INTAKE`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`
- [x] Optional: `ENABLE_WHATSAPP_PING=false`

### Data Security (PII / Retention)
- [x] `PII_REDACTION_ENABLED=true`
- [x] Review `PII_REDACTION_FIELDS` (default: phone,email,address,ssn,tax_id,passport,national_id,id_number)
- [x] Confirm retention policy + purge process (see `DATA_SECURITY_PLAN.md`)

### Webhooks
- [x] Stripe webhook: `https://vejapro.lt/api/v1/webhook/stripe`
  - Events: `payment_intent.succeeded`
- [x] Twilio webhook: `https://vejapro.lt/api/v1/webhook/twilio` (HTTP POST)
- [x] Twilio Voice webhook: `https://vejapro.lt/api/v1/webhook/twilio/voice`
- [x] Chat webhook: `https://vejapro.lt/api/v1/webhook/chat/events`

### Database
- [x] Alembic version is `20260209_000016` (latest — 16 migracijų, V2.2+V2.3)
- [x] Supabase backups enabled (auto or scheduled)
- [x] Test restore steps known (see Section 5)
- [x] Staging restore drill completed (2026-02-06)

### Mobile & CI/CD
- [x] Mobile responsiveness patikrinta visuose 11 HTML puslapiuose (2026-02-07)
- [x] CI/CD pipeline veikiantis (ruff lint + pytest + deploy su health check)
- [x] CI stabilizacija patikrinta (2026-02-08): ruff PASS, 73 testai PASS
- [x] V2.3 testai praėjo (2026-02-09): 114 passed, 13 naujų V2.3 testų, 0 regresijų

### Smoke Tests (prod — TEST raktai)
- [x] Create project → status `DRAFT`
- [x] Stripe DEPOSIT → status `PAID` (audit log `SYSTEM_STRIPE`)
- [x] Add 3 evidences for `EXPERT_CERTIFICATION`
- [x] Certify → status `CERTIFIED`
- [x] Stripe FINAL → SMS sent
- [x] Reply `TAIP <TOKEN>` → status `ACTIVE`
- **Pastaba:** Smoke test praėjo su TEST raktais (2026-02-06). Reikia pakartoti su LIVE raktais.

### Smoke Tests V2.3 (email confirmation flow)
- [x] Quick payment DEPOSIT → DRAFT→PAID (idempotencija 200, konfliktas 409)
- [x] Quick payment FINAL (CERTIFIED) → email_queued=true
- [x] `POST /public/confirm-payment/{token}` → CERTIFIED→ACTIVE (`SYSTEM_EMAIL`)
- [x] SSE metrics (`GET /admin/finance/metrics`) → grąžina daily_volume, manual_ratio
- [x] Finance disabled → 404 (ne 403)
- **Pastaba:** V2.3 smoke testai praėjo automatizuotai (2026-02-09, 13 testų).

### Smoke Tests (prod — LIVE raktai) — DAR NEATLIKTA
- [ ] Perjungti Stripe/Twilio/Supabase į LIVE raktus
- [ ] Pakartoti pilną srautą: DRAFT → PAID → CERTIFIED → ACTIVE
- [ ] Patikrinti tikrą SMS gavimą
- [ ] Patikrinti tikrą Stripe mokėjimą
- [ ] Patikrinti tikrą email confirmation (SMTP)

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
- `/admin/finance` — finansų modulis (V2.3: ledger, dokumentai, quick-payment)
- `/admin/ai` — AI monitoring dashboard

Public portals:
- `/` — viešas pradinis puslapis (lietuvių k.)
- `/gallery` — viešoji galerija
- `/client` — klientų portalas (JWT)
- `/contractor` — rangovo portalas (JWT)
- `/expert` — eksperto portalas (JWT)

> **Pastaba:** Visi puslapiai (admin ir public) yra mobile-responsive su @media queries (768px breakpoint) ir touch-friendly targets (44px).

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
