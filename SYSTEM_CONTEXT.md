# SYSTEM_CONTEXT

Trumpa santrauka, kur veikia VejaPRO sistema, kaip ji uzkurta ir kur ieskoti konfiguracijos.

## Aplinka
- Production/primary VM: `10.10.50.178` (Ubuntu).
- SSH vartotojas: `administrator`.
- Repo kelias VM viduje: `/home/administrator/VejaPRO`.
- Backend katalogas: `/home/administrator/VejaPRO/backend`.

## Paleidimas (production)
- Procesas valdomas per systemd:
  - Servisas: `vejapro.service`
  - Komandos: `systemctl status vejapro`, `systemctl restart vejapro`
- Uvicorn klausosi ant `0.0.0.0:8000`.
- Nginx reverse proxy:
  - Konfigai: `/etc/nginx/sites-available/vejapro` ir `/etc/nginx/sites-enabled/vejapro`
  - Logai: `/var/log/nginx/access.log`, `/var/log/nginx/error.log`

## Domenas / isorinis srautas
- Domenas: `https://vejapro.lt`
- Srautas eina per Nginx i `127.0.0.1:8000`.
- X-Forwarded-For naudojamas realiam IP.

## Konfiguracija (prod)
- Aplinkos failas: `/home/administrator/VejaPRO/backend/.env.prod`
- Svarbu (be reiksmu):
  - `DATABASE_URL` (Supabase Postgres)
  - `SUPABASE_JWT_SECRET`
  - `ADMIN_IP_ALLOWLIST` (CSV arba JSON lista)
  - `ADMIN_TOKEN_ENDPOINT_ENABLED`
  - `SECURITY_HEADERS_ENABLED`
  - `ALLOW_INSECURE_WEBHOOKS` (prod turetu buti `false`)
- **Niekada necommitinti paslapciu i repo.**

## Deploy (manual)
Tik su svariu working tree.
1. `ssh administrator@10.10.50.178`
2. `cd /home/administrator/VejaPRO`
3. `git status -sb` (turi buti svaru)
4. `git pull --rebase origin main`
5. `sudo systemctl restart vejapro`
6. Patikra:
   - `curl http://127.0.0.1:8000/health`
   - `curl https://vejapro.lt/health`
7. Logai jei reikia:
   - `journalctl -u vejapro -n 50 --no-pager`

### Greitas update per timeri
Alternatyva: `sudo systemctl start vejapro-update.service` (pull + restart).

## Rollback (manual)
Rollback daryti tik jei zinai kad ankstesnis commitas buvo stabilus.
1. Sustabdyk auto-update laikinai:
   - `sudo systemctl stop vejapro-update.timer`
2. Pasirink commit:
   - `git log --oneline`
3. Pereik i commit:
   - `git checkout <SHA>`
4. Restart:
   - `sudo systemctl restart vejapro`
5. Patikra (health):
   - `curl http://127.0.0.1:8000/health`
   - `curl https://vejapro.lt/health`
6. Kai problema istaisoma:
   - `git checkout main`
   - `git pull --rebase origin main`
   - `sudo systemctl restart vejapro`
   - `sudo systemctl start vejapro-update.timer`

## Admin prieiga ir tokenai
- Admin UI keliai: `/admin`, `/admin/projects`, `/admin/calls`, `/admin/calendar`, `/admin/audit`, `/admin/margins`.
- Token endpoint: `GET /api/v1/admin/token` veikia tik jei `ADMIN_TOKEN_ENDPOINT_ENABLED=true`.
- Jei rodoma **Access denied**, patikrink:
  - Ar IP yra `ADMIN_IP_ALLOWLIST`.
  - Ar Nginx teisingai perduoda `X-Forwarded-For`.

## Duombaze
- Production naudoja Supabase Postgres per `DATABASE_URL`.
- Testams galima naudoti SQLite (skaityk `backend/README.md`).

## Statiniai failai (UI)
- Admin ir landing HTML: `/home/administrator/VejaPRO/backend/app/static`.
- Admin UI yra statinis (be atskiros front-end build grandines).

## Servisai / Timeriai (prod)
- `vejapro-backup.timer` -> `/usr/local/bin/vejapro-backup`
- `vejapro-healthcheck.timer`
- `vejapro-diskcheck.timer`
- `vejapro-update.timer`

## Logu perziura
- Backend: `journalctl -u vejapro -f`
- Nginx: `/var/log/nginx/access.log`, `/var/log/nginx/error.log`

## Troubleshooting (dazniausios klaidos)
- **Cloudflare 502**:
  - Patikrink ar `vejapro` service gyvas:
    - `sudo systemctl status vejapro --no-pager`
    - `curl http://127.0.0.1:8000/health`
  - Paziurek logus:
    - `journalctl -u vejapro -n 50 --no-pager`
    - `sudo tail -n 50 /var/log/nginx/error.log`
- **Admin UI 401 Unauthorized**:
  - JWT pasenes ar neteisingas. Sugeneruok nauja:
    - `curl https://vejapro.lt/api/v1/admin/token` (tik is leidziamo IP)
  - Uztikrinti, kad header yra `Authorization: Bearer <TOKEN>`.
- **Admin UI 403 (IP not allowed)**:
  - Patikrink `ADMIN_IP_ALLOWLIST` (CSV arba JSON lista).
  - Patikrink Nginx real IP:
    - `/etc/nginx/snippets/cloudflare-realip.conf`
- **`ModuleNotFoundError: app` per Alembic**:
  - Naudok: `PYTHONPATH=backend alembic -c backend/alembic.ini upgrade head`
- **`SettingsError` is pydantic_settings**:
  - Blogas env formatas (pvz. admin_ip_allowlist). Taisyti `.env.prod`.
- **Stripe webhook 400**:
  - Testuose reikia `ALLOW_INSECURE_WEBHOOKS=true`.
  - Prode tikrinti `STRIPE_WEBHOOK_SECRET`.
- **Twilio 11200 / signature invalid**:
  - Patikrink `TWILIO_AUTH_TOKEN` ir `TWILIO_WEBHOOK_URL`.
  - Patikrink, kad atsakymas yra `Content-Type: application/xml`.
