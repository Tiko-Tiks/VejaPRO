# INFRASTRUCTURE

Tikslas: kad nereiketu kiekviena karta aiskinti, kur kas veikia. Sis failas yra trumpas "runbook" tiek zmogui, tiek AI agentui.

## Dabartinis modelis (Variantas 1)

- Koda redaguoji / commitini savo darbo kompiuteryje (Windows).
- GitHub yra vienintelis source of truth.
- Production ir Staging veikia **viename** Ubuntu VM (host alias: `veja-vm`, IP: `10.10.50.178`).
- Deploy vyksta is serverio: jis pats periodiskai pasiima naujausius pakeitimus is `origin/main` ir restartina servisa.

Tai reiskia: tau nereikia rankiniu budu daryti `git pull` serveryje kiekviena karta. Pakanka `git push`, o serveris atsinaujins pats (per kelias minutes).

## Kaip prisijungti (Windows)

Rekomenduojama tureti `~/.ssh/config` ir jungtis per alias:

```sshconfig
Host veja-vm
    HostName 10.10.50.178
    User administrator
    IdentityFile C:/Users/Administrator/.ssh/vejapro_ed25519
    IdentitiesOnly yes
```

Testas:

```powershell
ssh veja-vm "echo OK"
```

## Komponentai (Production VM)

### Cloudflare Tunnel

- `cloudflared.service` (systemd)
- Konfigas: `/etc/cloudflared/config.yml`
- Credentials: `/etc/cloudflared/vejapro.json`
- Ingress tipas: viskas eina i vietini Nginx (`http://127.0.0.1:80`), o Nginx paskirsto i backend portus.

### Nginx

- `nginx.service` (systemd)
- Vhostai:
  - `/etc/nginx/sites-available/vejapro` -> `vejapro.lt` (proxy i `127.0.0.1:8000`)
  - `/etc/nginx/sites-available/vejapro-staging` -> `staging.vejapro.lt` (proxy i `127.0.0.1:8001`)
- Realus kliento IP:
  - Nginx naudoja `/etc/nginx/snippets/cloudflare-realip.conf` (CF-Connecting-IP + Cloudflare IP ranges)
  - Nginx perduoda i backend per `X-Real-IP $remote_addr`
  - Backend admin allowlist tikrina **tik** `X-Real-IP` (ne X-Forwarded-For)

### Backend

- `vejapro.service` (production): `uvicorn app.main:app --port 8000`
- `vejapro-staging.service` (staging): `uvicorn app.main:app --port 8001`
- Repo kelias: `/home/administrator/VejaPRO`
- Virtualenv: `/home/administrator/.venv/`
- Env failai:
  - Production: `/home/administrator/VejaPRO/backend/.env`
  - Staging: `/home/administrator/VejaPRO/backend/.env.staging`
  - `/home/administrator/VejaPRO/backend/.env.prod` yra **symlink i `.env`**, nes backup skriptas istoriskai skaito `.env.prod`

## Deploy workflow (kaip realiai vyksta)

### Auto deploy (numatytasis)

Production VM turi systemd timerius, kurie periodiskai atnaujina koda is GitHub.

- Pagrindinis: `vejapro-update.timer` -> `/usr/local/bin/vejapro-update`
- Taip pat egzistuoja: `vejapro-pull.timer` (kas 2 min) -> `git pull --rebase` + `systemctl restart vejapro`

Pastaba: geriausia tureti tik viena "auto-pull" mechanizma, bet siuo metu veikia abu. Jei pastebi bereikalingus restartus, rekomendacija yra isjungti `vejapro-pull.timer` ir palikti tik `vejapro-update.timer`.

### Manual deploy (kai nori iskart)

Interaktyviai per SSH (reikia sudo):

```bash
sudo systemctl start vejapro-update.service
```

Patikra:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS https://vejapro.lt/health
```

## Alembic migracijos

Migracijos paleidziamos tik serveryje. Komanda:

```bash
ssh veja-vm "cd /home/administrator/VejaPRO && \
  source /home/administrator/.venv/bin/activate && \
  cd backend && alembic upgrade head"
```

Migracijos statusas:

```bash
ssh veja-vm "cd /home/administrator/VejaPRO && \
  source /home/administrator/.venv/bin/activate && \
  cd backend && alembic current"
```

**Svarbu:** auto-deploy skriptas (`vejapro-update`) migraciju **nevykdo** — reikia paleisti rankiniu budu po kiekvieno `alembic revision`.

## Atsaukimas (Rollback)

Jei naujausias deploy sugriauna produkcija:

### 1. Greitas atsaukimas (revert i pries tai buvusi commit)

```bash
ssh veja-vm "cd /home/administrator/VejaPRO && \
  git log --oneline -5 && \
  git revert HEAD --no-edit && \
  sudo systemctl restart vejapro"
```

### 2. Tikslinis atsaukimas (i konkretu commit)

```bash
ssh veja-vm "cd /home/administrator/VejaPRO && \
  git checkout <commit-sha> -- backend/ && \
  sudo systemctl restart vejapro"
```

### 3. Alembic migraciju atsaukimas

```bash
ssh veja-vm "cd /home/administrator/VejaPRO && \
  source /home/administrator/.venv/bin/activate && \
  cd backend && alembic downgrade -1"
```

**Pastaba:** visuomet pirma atsakyk migracija, po to revertink koda.

## Dazniausios problemos

| Problema | Diagnoze | Sprendimas |
|----------|----------|------------|
| Backend neatsako | `systemctl status vejapro` | `sudo systemctl restart vejapro` |
| 502 Bad Gateway | `ss -lntp \| grep 8000` — ar klausosi? | Restartink backend arba tikrink `.env` |
| Cloudflare tunnel down | `systemctl status cloudflared` | `sudo systemctl restart cloudflared` |
| Nginx klaida | `nginx -t` — config testas | Sutaisyk config, `sudo systemctl reload nginx` |
| Senas kodas po push | `git log -1` serveryje — ar atsinaujino? | `sudo systemctl start vejapro-update.service` |
| Migracija nepavyko | `alembic current` — kur sustojo? | `alembic upgrade head` arba `alembic downgrade -1` |
| `.env` klaida | `journalctl -u vejapro -n 50` | Tikrink `.env` kintamuosius, restartink |
| Testai luzta CI | Patikrink `.github/workflows/ci.yml` env vars | Pridek trukstamus feature flags |

## Greita diagnostika (naudinga agentui)

```bash
systemctl status vejapro --no-pager -l
systemctl status nginx cloudflared --no-pager -l
systemctl list-timers --all --no-pager | egrep 'vejapro|cloudflared' || true
ss -lntp | sed -n '1,40p'
```

## Kur detales

- Detalesnis runbook: `SYSTEM_CONTEXT.md`
- Admin UI V3: `backend/docs/ADMIN_UI_V3.md`

