# Deployment Notes 2026-02-04 (VejaPRO backend)

Date: 2026-02-04
Scope: backend + infra wiring (DB, Stripe, Twilio, Cloudflare/Nginx)

## Summary
- Backend is running on Ubuntu VM via systemd (uvicorn), behind Nginx.
- Public access is through Cloudflare Tunnel and domain `vejapro.lt`.
- Supabase Postgres is used as DATABASE_URL.
- Stripe and Twilio webhooks are working end-to-end.

## Environment (prod)
- VM: Ubuntu 25.04 (host: 10.10.50.178)
- Service: `vejapro.service`
- App listen: `0.0.0.0:8000`
- Nginx reverse proxy on 80/443
- Cloudflare Tunnel: CNAME `vejapro.lt` and `www` -> `*.cfargotunnel.com`

## Configuration changes (code)
- Twilio webhook URL override in settings:
  - `TWILIO_WEBHOOK_URL` added (uses exact public URL for signature validation)
- Twilio webhook now always returns TwiML XML:
  - Response body: `<Response></Response>`
  - Content-Type: `application/xml`
- Alembic config now escapes `%` in DATABASE_URL to avoid ConfigParser interpolation.

## Configuration (env)
Required env keys in `/home/administrator/VejaPRO/backend/.env.prod`:
- `DATABASE_URL` (Supabase Postgres, sslmode=require)
- `SUPABASE_JWT_SECRET`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`
- `TWILIO_WEBHOOK_URL=https://vejapro.lt/api/v1/webhook/twilio`

## Database state
- Alembic version: `20260203_000002`
- Tables present: users, projects, audit_logs, evidences, payments, sms_confirmations, margins
- Notes:
  - Inserted test evidences for certification flow using SQL (see tests below).

## Tests executed
### Unit + API tests (local)
- `PYTHONPATH=backend python -m pytest backend/tests -q`
- `PYTHONPATH=backend python -m pytest backend/tests/api -q`

### Manual end-to-end flow (prod)
1. Create project (DRAFT)
2. Stripe payment (DEPOSIT) -> status becomes PAID (webhook)
3. Transition to SCHEDULED -> PENDING_EXPERT
4. Add 3 evidences of category `EXPERT_CERTIFICATION`
5. `POST /api/v1/certify-project` -> status CERTIFIED
6. Stripe payment (FINAL) -> SMS confirmation token created + SMS sent
7. SMS reply `TAIP <TOKEN>` -> status ACTIVE

Evidence insert used during test:
```
INSERT INTO evidences (
  id, project_id, file_url, category, uploaded_at, created_at, show_on_web, is_featured
)
VALUES
  (gen_random_uuid(), '$PROJECT_ID', 'https://example.com/a.jpg', 'EXPERT_CERTIFICATION', now(), now(), false, false),
  (gen_random_uuid(), '$PROJECT_ID', 'https://example.com/b.jpg', 'EXPERT_CERTIFICATION', now(), now(), false, false),
  (gen_random_uuid(), '$PROJECT_ID', 'https://example.com/c.jpg', 'EXPERT_CERTIFICATION', now(), now(), false, false);
```

## Verified outcomes
- `GET https://vejapro.lt/health` -> 200 OK
- Stripe webhook updates project status and audit logs show `SYSTEM_STRIPE` actions
- Twilio webhook accepts inbound messages and logs `SYSTEM_TWILIO` actions
- Full flow ends with project status `ACTIVE`

## Known follow-ups (optional)
- Consider adding a simple admin UI for monitoring projects / audit logs
- Optional: tighten nginx proxy headers and limits
