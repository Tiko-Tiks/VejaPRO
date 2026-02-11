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
- `/deploy --changed` — auto-detect and deploy all modified tracked files

## Step 1: Determine files to deploy

If user specifies files, use those. If `--changed`, detect with:

```bash
git diff --name-only HEAD
git status --porcelain | grep '^ M\|^M\|^A' | awk '{print $2}'
```

Only deploy files under `backend/`. Skip `.env`, `__pycache__`, `.pyc`.

## Step 2: Confirm with user

Show the list of files to deploy and ask for confirmation:

```
Files to deploy:
  1. backend/app/api/v1/projects.py
  2. backend/app/services/transition_service.py
Proceed? (y/n)
```

## Step 3: Upload via SCP

For each file:

```bash
scp -i "C:/Users/Administrator/.ssh/vejapro_ed25519" \
  "C:/Users/Administrator/Desktop/VejaPRO/{path}" \
  administrator@10.10.50.178:/tmp/{filename}
```

For 3+ files, batch them in a single scp call:

```bash
scp -i "C:/Users/Administrator/.ssh/vejapro_ed25519" \
  file1 file2 file3 \
  administrator@10.10.50.178:/tmp/
```

## Step 4: Replace on server

Single SSH call with all replacements chained:

```bash
ssh -i "C:/Users/Administrator/.ssh/vejapro_ed25519" administrator@10.10.50.178 \
  "rm /home/administrator/VejaPRO/{path1} 2>/dev/null; cp /tmp/{file1} /home/administrator/VejaPRO/{path1} && \
   rm /home/administrator/VejaPRO/{path2} 2>/dev/null; cp /tmp/{file2} /home/administrator/VejaPRO/{path2}"
```

Note: Use `rm ... 2>/dev/null; cp ...` (not `&&`) — rm may fail for new files, that's OK.

## Step 5: Verify and report

After deploy, run a quick health check:

```bash
ssh -i "C:/Users/Administrator/.ssh/vejapro_ed25519" administrator@10.10.50.178 \
  "curl -sf http://localhost:8000/health || echo 'HEALTH CHECK FAILED'"
```

Report:
- Files deployed successfully
- Health check result
- Remind: auto-deploy from main runs every 5 min — manual deploy is for hotfixes or branch testing

## Rules

- Local base path: `C:\Users\Administrator\Desktop\VejaPRO\`
- Server base path: `/home/administrator/VejaPRO/`
- Root-owned files: `rm` then `cp` from `/tmp/` (no sudo password)
- Never deploy `.env` files
- After deploying static HTML/CSS, remind about browser cache (Ctrl+Shift+R)
