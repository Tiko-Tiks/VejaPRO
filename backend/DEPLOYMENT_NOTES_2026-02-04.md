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

## Live configuration summary (where things live)
- Systemd service file: `/etc/systemd/system/vejapro.service`
- Env file used by service: `/home/administrator/VejaPRO/backend/.env.prod`
- Nginx site: `/etc/nginx/sites-available/vejapro` (enabled via sites-enabled)
- Cloudflare real IPs: `/etc/nginx/snippets/cloudflare-realip.conf`
- Cloudflare Tunnel config: `/etc/cloudflared/config.yml`
- Cloudflare Tunnel credentials: `/etc/cloudflared/vejapro.json`

## Webhook endpoints used by integrations
- Stripe webhook URL: `https://vejapro.lt/api/v1/webhook/stripe`
  - Events handled in code: `payment_intent.succeeded`
- Twilio webhook URL: `https://vejapro.lt/api/v1/webhook/twilio`
  - Expecting form-encoded body (`From`, `Body`, etc.)
  - Response: TwiML XML (`<Response></Response>`)

## Admin IP allowlist (optional)
You can restrict admin UI/API access by IP:

```
ADMIN_IP_ALLOWLIST=216.128.1.48,10.10.50.0/24
```

If empty, all IPs are allowed.

## AI assistant / Call assistant status
- AI assistant is **not deployed**. It is defined in documentation as a future phase.
  - Flags exist but are **OFF** in production:
    - `ENABLE_VISION_AI=false`
    - `ENABLE_ROBOT_ADAPTER=false`
- Call assistant (voice/phone bot) is **not implemented**.
  - Current Twilio integration is **SMS-only** (confirmation flow).
  - No voice/TwiML call flow is wired in backend.

## How to generate a short-lived admin JWT (for manual testing)
```
python - <<'PY'
import os, jwt, time
secret = os.environ["SUPABASE_JWT_SECRET"]
payload = {
    "sub": "00000000-0000-0000-0000-000000000001",
    "email": "admin@test.local",
    "app_metadata": {"role": "ADMIN"},
    "iat": int(time.time()),
    "exp": int(time.time()) + 3600,
}
print(jwt.encode(payload, secret, algorithm="HS256"))
PY
```

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

## Manual API examples (copy-paste)
Set variables:
```
export BASE_URL="https://vejapro.lt"
export TOKEN="PASTE_JWT_HERE"
```

Create project:
```
curl -s -X POST "$BASE_URL/api/v1/projects" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"client_info":{"name":"Demo","client_id":"demo-1","phone":"+37060000000"}}'
```

Transition status:
```
curl -s -X POST "$BASE_URL/api/v1/transition-status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"entity_type":"project","entity_id":"<PROJECT_ID>","new_status":"SCHEDULED","actor":"ADMIN"}'
```

Stripe test payment (DEPOSIT):
```
curl https://api.stripe.com/v1/payment_intents \
  -u "$STRIPE_SECRET_KEY:" \
  -d amount=1000 \
  -d currency=eur \
  -d "payment_method_types[]=card" \
  -d payment_method=pm_card_visa \
  -d confirm=true \
  -d "metadata[project_id]=<PROJECT_ID>" \
  -d "metadata[payment_type]=DEPOSIT"
```

Stripe test payment (FINAL):
```
curl https://api.stripe.com/v1/payment_intents \
  -u "$STRIPE_SECRET_KEY:" \
  -d amount=1000 \
  -d currency=eur \
  -d "payment_method_types[]=card" \
  -d payment_method=pm_card_visa \
  -d confirm=true \
  -d "metadata[project_id]=<PROJECT_ID>" \
  -d "metadata[payment_type]=FINAL"
```

Project state + audit logs:
```
curl -s "$BASE_URL/api/v1/projects/<PROJECT_ID>" \
  -H "Authorization: Bearer $TOKEN"

curl -s "$BASE_URL/api/v1/audit-logs?limit=5" \
  -H "Authorization: Bearer $TOKEN"
```

## Verified outcomes
- `GET https://vejapro.lt/health` -> 200 OK
- Stripe webhook updates project status and audit logs show `SYSTEM_STRIPE` actions
- Twilio webhook accepts inbound messages and logs `SYSTEM_TWILIO` actions
- Full flow ends with project status `ACTIVE`

## Go-live checklist
1. Cloudflare
   - `vejapro.lt` + `www` CNAME to Cloudflare Tunnel (`*.cfargotunnel.com`)
   - No legacy A records pointing elsewhere
2. Nginx
   - HTTPS enabled and proxy to `127.0.0.1:8000`
   - Real IP config for Cloudflare in place
3. Backend env
   - `.env.prod` has LIVE keys (Stripe/Twilio/Supabase)
   - `TWILIO_WEBHOOK_URL` uses `https://vejapro.lt/api/v1/webhook/twilio`
4. Stripe (LIVE)
   - Webhook endpoint created at `https://vejapro.lt/api/v1/webhook/stripe`
   - Events enabled: `payment_intent.succeeded`
5. Twilio (LIVE)
   - Phone number points to `https://vejapro.lt/api/v1/webhook/twilio` (HTTP POST)
   - Sender number set in `TWILIO_FROM_NUMBER`
6. Smoke tests
   - `/health` returns 200
   - DEPOSIT moves DRAFT -> PAID
   - FINAL triggers SMS and allows `TAIP <TOKEN>` to activate

## Known follow-ups (optional)
- Consider adding a simple admin UI for monitoring projects / audit logs
- Optional: tighten nginx proxy headers and limits
