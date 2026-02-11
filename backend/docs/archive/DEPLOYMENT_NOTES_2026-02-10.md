# Deployment Notes (2026-02-10)

## Kontekstas

Tikslas buvo supaprastinti "kas kur veikia" (onboarding) ir sutvarkyti pastebetus infrastruktūros neatitikimus production VM.

## Faktine situacija (production VM: 10.10.50.178)

- `cloudflared.service` aktyvus, konfigas `/etc/cloudflared/config.yml` -> ingress i `http://127.0.0.1:80`
- `nginx.service` aktyvus, proxy:
  - `vejapro.lt` -> `127.0.0.1:8000`
  - `staging.vejapro.lt` -> `127.0.0.1:8001`
- Backend:
  - `vejapro.service` (prod)
  - `vejapro-staging.service` (staging)
- Deploy timeriai:
  - `vejapro-update.timer` (kas ~5 min) -> `/usr/local/bin/vejapro-update`
  - `vejapro-pull.timer` (kas ~2 min) -> `git pull --rebase` + `systemctl restart vejapro` (legacy)

## Pakeitimai / sutvarkymai

### 1) Backup env failas (fix)

Rasta problema: `vejapro-backup.service` (timeris kasdien 02:15) failino, nes skriptas bande source'inti:

- `/home/administrator/VejaPRO/backend/.env.prod` (failas buvo istrintas / nebuvo).

Fix: production VM sukurtas symlink, kad backup visada naudotu ta pati env kaip ir backend:

- `/home/administrator/VejaPRO/backend/.env.prod` -> `.env`

Pastaba: `vejapro-backup` skriptas kuria backup'us i `/var/backups/vejapro` (root-only).

### 2) Dokumentacija (repo)

Papildyta / atnaujinta, kad onboarding butu greitesnis:

- Naujas: `INFRASTRUCTURE.md` (trumpas runbook, ka skaityti pirma)
- Atnaujinta: `SYSTEM_CONTEXT.md` (Python/venv keliai, timeriai, `.env.prod` symlink logika)

## Rizikos / rekomendacijos

- Rekomenduojama tureti tik viena auto-update mechanizma (palikti `vejapro-update.timer`, isjungti `vejapro-pull.timer`), kad isvengti dubliuotu restartu.

## 2026-02-11 Hardening follow-up

Tiksliniai veiksmai po admin UI redesign:

1. `HEAD /health` support pridetas aplikacijoje (`backend/app/main.py`), kad health probe galetu naudoti lengvesni patikrinima.
2. Pridetas `STAGING_IP_ALLOWLIST` (config + middleware), kad staging aplinka galetu buti apribota pagal `X-Real-IP`.
3. Security headers sprendimas: paliekame edge (Nginx) kaip pagrindini saltini staging aplinkai, kad nebutu dubliuotu header'iu.

Root komandos production/staging VM (vykdyti su `sudo`):

```bash
sudo systemctl disable --now vejapro-pull.timer
sudo systemctl daemon-reload

sudo tee /usr/local/bin/vejapro-healthcheck >/dev/null <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

URL="http://127.0.0.1:8000/health"
if ! curl -fsSI --max-time 3 "$URL" >/dev/null; then
  systemctl restart vejapro
  logger -t vejapro-healthcheck "Health failed (HEAD /health), restarted service"
fi
EOF
sudo chmod +x /usr/local/bin/vejapro-healthcheck
sudo systemctl restart vejapro-healthcheck.timer

# Staging IP limit per Nginx (example subnet, adjust to real admin IP/CIDR)
sudo sed -i '/server_name staging.vejapro.lt;/a\    allow 10.10.50.0/24;\n    deny all;' /etc/nginx/sites-available/vejapro-staging

# Optional: remove duplicate security headers from staging Nginx if app headers are enabled
# (keep exactly one header source in final setup).
sudo nginx -t && sudo systemctl reload nginx
```
