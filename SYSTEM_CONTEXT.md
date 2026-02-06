# SYSTEM_CONTEXT

Trumpa santrauka, kur veikia VejaPRO sistema, kaip ji uzkurta ir kur ieskoti konfiguracijos.

## Aplinka (dvi masinos)

### Development (Windows)
- OS: Windows 10 (10.0.17763).
- IDE: Cursor (su AI agentu).
- Repo kelias: `C:\Users\Administrator\Desktop\VejaPRO`.
- Shell: PowerShell.
- Python: **nera pilnos aplinkos** — negalima paleisti backend'o ar testu tiesiogiai.
- Paskirtis: kodo redagavimas, code review, git operacijos, SSH i serveri.

### Production / Staging (Ubuntu)
- Production VM: `10.10.50.178` (Ubuntu 25.04, kernel 6.14).
- SSH vartotojas: `administrator`.
- Repo kelias VM viduje: `/home/administrator/VejaPRO`.
- Backend katalogas: `/home/administrator/VejaPRO/backend`.
- Python: 3.12.2 (virtualenv `/home/administrator/.venv/`).
- Visos priklausomybes (FastAPI, SQLAlchemy, pytest ir kt.) idiegtos virtualenv viduje.
- Paskirtis: backend vykdymas, testu paleidimas, deploy.

### SSH prisijungimas is Windows i Ubuntu
- Raktas: `%USERPROFILE%\.ssh\vejapro_ed25519` (Ed25519).
- Komanda: `ssh -i %USERPROFILE%\.ssh\vejapro_ed25519 administrator@10.10.50.178`
- **Svarbu:** serveris limituoja SSH prisijungimu kieki (MaxStartups / fail2ban).
  Jei gaunate `Connection reset` arba `banner exchange` klaida — palaukite ~60s ir bandykite vel.
  Nesiuskite keliu SSH sesiju vienu metu.

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
- X-Real-IP (arba paskutinis X-Forwarded-For) naudojamas realiam IP.

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

## Konfiguracija (staging)
- Aplinkos failas: `/home/administrator/VejaPRO/backend/.env.staging`
- Failas nera repo, todel `git pull` jo neatnaujina (kopijuoti rankiniu budu).
- Staging service naudoja atskira Supabase projekta.

## Deploy

### Automatinis deploy (numatytasis)
Ubuntu serveris kas 5 min automatiskai tikrina ar yra nauju pakeitimu `origin/main`.
- Timeris: `vejapro-update.timer` (kas 5 min + iki 30s atsitiktinis delsa).
- Servisas: `vejapro-update.service` -> skriptas `/usr/local/bin/vejapro-update`.
- Skriptas:
  1. Tikrina ar working tree svarus (jei ne — praleidzia).
  2. `git fetch origin main` + palygina su HEAD.
  3. Jei yra pakeitimu: `git pull --rebase origin main` + `systemctl restart vejapro`.
  4. Jei nera — nieko nedaro.
- SSH raktas serveryje: `/home/administrator/.ssh/veja_deploy`.

**Iprastas workflow:**
1. Redaguoji koda Windows (Cursor).
2. `git push origin main`.
3. Per ~5 min serveris automatiskai pasitraukia ir restart'ina.
4. Patikrink: `https://vejapro.lt/health`.

### Rankinis deploy (skubus)
Kai nori deploy is karto, nelaukiant timerio:

**Budas 1 — paleidzi update servisa (rekomenduojama):**
```
ssh -i %USERPROFILE%\.ssh\vejapro_ed25519 administrator@10.10.50.178 "sudo systemctl start vejapro-update.service && sleep 5 && curl -s http://127.0.0.1:8000/health"
```

**Budas 2 — rankinis pull + restart:**
```
ssh -i %USERPROFILE%\.ssh\vejapro_ed25519 administrator@10.10.50.178 "cd /home/administrator/VejaPRO && git pull --rebase origin main && sudo systemctl restart vejapro && sleep 3 && curl -s http://127.0.0.1:8000/health"
```

**Budas 3 — interaktyviai per SSH:**
1. `ssh -i %USERPROFILE%\.ssh\vejapro_ed25519 administrator@10.10.50.178`
2. `cd /home/administrator/VejaPRO`
3. `git status -sb` (turi buti svaru)
4. `git pull --rebase origin main`
5. `sudo systemctl restart vejapro`
6. Patikra: `curl http://127.0.0.1:8000/health`
7. Logai: `journalctl -u vejapro -n 50 --no-pager`

### Testu paleidimas (is Windows per SSH)
```
ssh -i %USERPROFILE%\.ssh\vejapro_ed25519 administrator@10.10.50.178 "cd /home/administrator/VejaPRO && PYTHONPATH=backend /home/administrator/.venv/bin/python -m pytest backend/tests -q"
```

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

## Staging serveris (portas 8001)
- systemd service: `vejapro-staging.service`
- Uvicorn: `0.0.0.0:8001`
- Nginx vhost: `/etc/nginx/sites-available/vejapro-staging`
- Cloudflared ingress turi tureti `staging.vejapro.lt` -> `http://127.0.0.1:80`
- Health: `https://staging.vejapro.lt/health`
