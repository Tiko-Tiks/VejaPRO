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
- Python: 3.12.2 (virtualenv `/home/administrator/VejaPRO/.venv/`).
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

## Portalai (visi vartotojai)
- **Viešas pradinis puslapis:** `/` (landing.html)
- **Galerija:** `/gallery` (gallery.html) — viešai prieinamas
- **Klientų portalas:** `/client` (client.html) — autentifikuotas per JWT
- **Rangovo portalas:** `/contractor` (contractor.html) — autentifikuotas per JWT
- **Eksperto portalas:** `/expert` (expert.html) — autentifikuotas per JWT
- **Web chat:** `/chat` (chat.html) — viesai prieinamas testavimo widget

## Duombaze
- Production naudoja Supabase Postgres per `DATABASE_URL`.
- Testams galima naudoti SQLite (skaityk `backend/README.md`).
- Dabartine Alembic versija: `20260208_000014` (14 migracijos, nuo `000001_init_core_schema` iki `000014_finance_ledger_core`).

## Statiniai failai (UI)
- Visi HTML failai: `/home/administrator/VejaPRO/backend/app/static`.
- UI yra statinis (be atskiros front-end build grandinės).
- **Kalba:** visa vartotojo sąsaja yra lietuvių kalba (`lang="lt"`).
- **i18n statusas (2026-02-07):** Pilnai sulietuvinti visi 11 HTML failų:
  - `landing.html` — viešas pradinis puslapis
  - `admin.html` — administravimo apžvalga
  - `projects.html` — projektų valdymas
  - `client.html` — klientų portalas
  - `audit.html` — audito žurnalas
  - `calls.html` — skambučių užklausos
  - `calendar.html` — kalendorius
  - `margins.html` — maržų taisyklės
  - `gallery.html` — viešoji galerija
  - `contractor.html` — rangovo portalas
  - `expert.html` — eksperto portalas
  - `chat.html` — web chat widget
  - `finance.html` — finansų knyga (Admin Finance UI)
- Visur naudojami teisingi lietuviški diakritikai (ą, č, ę, ė, į, š, ų, ū, ž).
- Navigacija admin puslapiuose vienoda: Apžvalga, Projektai, Skambučiai, Kalendorius, Auditas, Maržos.

### Mobilusis dizainas (responsive)
Visi 11 HTML failai turi mobile-first responsive dizainą:
- `@media (max-width: 768px)` ir `@media (max-width: 480px)` breakpoints
- Touch targets: min 44px mygtukai ir input laukai
- Lentelės mobiliuose konvertuojamos į korteles per `data-label` atributus
- Portalai: admin, audit, projects, calls, calendar, margins, client, contractor, expert, gallery, landing

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
  - Patikrink `TWILIO_AUTH_TOKEN` ir `TWILIO_WEBHOOK_URL` (SMS webhook).
  - Jei naudojamas skambuciu asistentas, patikrink `TWILIO_VOICE_WEBHOOK_URL` (Voice webhook).
  - Patikrink, kad atsakymas yra `Content-Type: application/xml`.

## CI/CD (GitHub Actions)
- **CI** (`.github/workflows/ci.yml`):
  - `lint` job: ruff check + ruff format (Python 3.12). **PRIVALO praiti prieš testus.**
  - `tests` job (`needs: lint`): SQLite test DB, in-process FastAPI app per `httpx.ASGITransport`, pytest -v --tb=short
  - Pastaba: serverio startuoti nereikia (nÄ—ra `BASE_URL`).
  - Jei norima testuoti per realÅ³ serverÄÆ: `USE_LIVE_SERVER=true` + `BASE_URL=http://127.0.0.1:8001` (opt-in).
  - Feature flags CI env: ENABLE_CALL_ASSISTANT, ENABLE_CALENDAR, ENABLE_SCHEDULE_ENGINE, ENABLE_NOTIFICATION_OUTBOX, ENABLE_VISION_AI, ADMIN_TOKEN_ENDPOINT_ENABLED, ADMIN_IP_ALLOWLIST
- Deprecated/pašalinta iš konfig: `AUDIT_LOG_RETENTION_DAYS`, `ENABLE_ROBOT_ADAPTER` (šie raktai nebevartojami ir yra ignoruojami).
- **Deploy** (`.github/workflows/deploy.yml`):
  - Manual dispatch su target pasirinkimu: production / staging / both
  - SSH → git pull → systemctl restart vejapro.service / vejapro-staging.service
  - Health check: `sleep 5` + `systemctl is-active`, journalctl logai (n 30) jei nepavyko
  - appleboy/ssh-action@v1.2.0, command_timeout: 120s
  - Input injection apsauga: `${{ inputs.target }}` perduodamas per `envs: DEPLOY_TARGET`
- **Linting** (`ruff.toml` repo root):
  - Taisyklės: E, W, F, I (isort), B, UP
  - Ignoruojama: E501, B008, UP017, UP012, UP045
  - `known-first-party = ["app"]`
  - Import tvarka: stdlib → third-party → local, abėcėliškai kiekvienoje grupėje
  - Migracijos (`backend/app/migrations/`) — visos taisyklės ignoruojamos

## Staging serveris (portas 8001)
- systemd service: `vejapro-staging.service`
- Uvicorn: `0.0.0.0:8001`
- Nginx vhost: `/etc/nginx/sites-available/vejapro-staging`
- Cloudflared ingress turi tureti `staging.vejapro.lt` -> `http://127.0.0.1:80`
- Health: `https://staging.vejapro.lt/health`

## Schedule Engine Env Additions (2026-02-07)
Prideti backend konfig raktai:
- `ENABLE_SCHEDULE_ENGINE`
- `HOLD_DURATION_MINUTES`
- `SCHEDULE_PREVIEW_TTL_MINUTES`
- `SCHEDULE_USE_SERVER_PREVIEW`
- `SCHEDULE_DAY_NAMESPACE_UUID`

## Notification / Workers Env Additions (2026-02-07)
- `ENABLE_NOTIFICATION_OUTBOX` — asinchronine pranesimu eile (SMS/WhatsApp/Telegram)
- `ENABLE_RECURRING_JOBS` — background workeriai (hold expiry, outbox dispatch)
- `SCHEDULE_HOLD_EXPIRY_INTERVAL_SECONDS` (default 60) — hold expiry worker intervalas

Prideti admin endpointai:
- `POST /api/v1/admin/schedule/reschedule/preview`
- `POST /api/v1/admin/schedule/reschedule/confirm`
- `POST /api/v1/admin/schedule/holds`
- `POST /api/v1/admin/schedule/holds/confirm`
- `POST /api/v1/admin/schedule/holds/cancel`
- `POST /api/v1/admin/schedule/holds/expire` (ADMIN-only)
- `POST /api/v1/admin/schedule/daily-approve`

Pastaba: modulis aktyvuojamas tik kai `ENABLE_SCHEDULE_ENGINE=true`.

## Finance Module Env Additions (2026-02-08)
- `ENABLE_FINANCE_LEDGER` — finansu knyga (ledger CRUD, suvestines, reversal)
- `ENABLE_FINANCE_AI_INGEST` — dokumentu upload + AI ekstrakcija
- `ENABLE_FINANCE_AUTO_RULES` — automatinis vendor taisykliu pritaikymas

Prideti admin endpointai:
- `POST /api/v1/admin/finance/ledger` — sukurti irasa
- `GET /api/v1/admin/finance/ledger` — saraso su paginacija
- `POST /api/v1/admin/finance/ledger/{id}/reverse` — koregavimas
- `GET /api/v1/admin/finance/summary` — periodo suvestine
- `GET /api/v1/admin/finance/projects/{id}` — projekto suvestine
- `POST /api/v1/admin/finance/quick-payment` — greitas mokejimas + status transition
- `POST /api/v1/admin/finance/documents` — dokumento upload (SHA-256 dedup)
- `GET /api/v1/admin/finance/documents` — dokumentu sarasas
- `POST /api/v1/admin/finance/documents/{id}/extract` — AI ekstrakcija
- `POST /api/v1/admin/finance/documents/{id}/post` — post to ledger
- `POST /api/v1/admin/finance/documents/bulk-post` — bulk post
- `POST /api/v1/admin/finance/vendor-rules` — tiekeju taisykles CRUD
- `GET /api/v1/admin/finance/vendor-rules` — tiekeju taisykliu sarasas

Admin UI: `/admin/finance` (finance.html) — 3 tab'ai: Knygos irasai, Dokumentai, Tiekeju taisykles + suvestine.

Admin UI:
- `/admin/calendar` turi "Hold įrankiai (Voice/Chat)" ir "Perplanavimas (RESCHEDULE)" bloką, skirtą testuoti Schedule Engine endpointus per UI.
