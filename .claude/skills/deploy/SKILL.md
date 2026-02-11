---
name: deploy
description: Deploy files to the remote VejaPRO server via SCP + SSH
disable-model-invocation: true
---

# Deploy Files to Server

Deploy local files to the remote VejaPRO server at `10.10.50.178`.

## Usage

- `/deploy backend/app/api/v1/projects.py` — deploy a single file
- `/deploy backend/app/static/admin-shared.css backend/app/static/admin.html` — deploy multiple files
- `/deploy backend/app/static/*.html` — deploy by glob pattern

## Workflow

For each file to deploy:

1. **SCP to /tmp/**:
   ```bash
   scp -i "C:/Users/Administrator/.ssh/vejapro_ed25519" "<local-path>" \
     administrator@10.10.50.178:/tmp/<filename>
   ```

2. **SSH to replace** (rm old + cp new — handles root-owned files):
   ```bash
   ssh -i "C:/Users/Administrator/.ssh/vejapro_ed25519" administrator@10.10.50.178 \
     "rm /home/administrator/VejaPRO/<relative-path> && cp /tmp/<filename> /home/administrator/VejaPRO/<relative-path>"
   ```

## Rules

- **Always confirm** with the user before executing — show list of files to deploy.
- Local paths are relative to `C:\Users\Administrator\Desktop\VejaPRO\`.
- Server paths mirror local: `backend/app/api/v1/projects.py` → `/home/administrator/VejaPRO/backend/app/api/v1/projects.py`.
- Root-owned files: `rm` then `cp` from `/tmp/` (no sudo password available).
- After deploy, remind: systemd auto-deploy polls main every 5 min — if this is a hotfix, the server already has it deployed now; if from a branch, it won't auto-deploy.
- For bulk deploys (5+ files), batch the SCP commands and SSH commands for efficiency.
