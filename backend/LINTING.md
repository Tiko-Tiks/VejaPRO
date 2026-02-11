# Linting / Formatting (CI)

CI blokuoja merges jei formatavimas arba lint taisykles nepraeina.

## Ka CI paleidzia

```bash
ruff check backend/
ruff format backend/ --check --diff
```

**Ruff versija:** `ruff==0.15.0` (prisegta `ci.yml` — nenaudoti kitos versijos).

## Konfiguracija

Failas: `ruff.toml` (repo root). Python target: 3.12. Line length: 120.

**Taisykles:** E (pycodestyle), W (warnings), F (pyflakes), I (isort), B (bugbear), UP (pyupgrade)

**Ignoruojamos:**
- `UP045` — naudoti `Optional[X]`, ne `X | None` (FastAPI konvencija)
- `UP017` — naudoti `timezone.utc`, ne `datetime.UTC` (codebase standartas)
- `UP012` — `.encode("utf-8")` leidziamas (eksplicitinis)
- `B008` — `Depends()` default argumentuose (FastAPI pattern)
- `E501` — ilgos eilutes (formatter tvarko)

Migracijos (`backend/app/migrations/`) — visos `ruff check` taisykles ignoruojamos, bet `ruff format` vis tiek tikrina.

## Import tvarka (I001 — CI blokuoja jei nesurikiuota)

```python
# 1. Standard library (import, tada from — abecéliskai)
import base64
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

# 2. Third-party (import, tada from — abecéliskai)
import jwt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

# 3. Local (import, tada from — abecéliskai)
import app.api.v1.projects as projects_module
from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.models.project import AuditLog, Evidence, Project
```

**Svarbu:** nariai `from X import A, B, C` taip pat turi buti abecéliskai.

## Tipu anotacijos (UP006/UP035)

- **NENAUDOTI** `typing.List`, `typing.Dict`, `typing.Tuple` anotacijoms.
- Naudoti `list[...]`, `dict[...]`, `tuple[...]`.
- Is `typing` dazniausia importuojam tik `Any` ir (pas mus) `Optional`.
- `class X(str, Enum)` -> naudoti `enum.StrEnum` (UP042).

## Dazniausioss CI klaidos (greitas fix)

### Ruff I001 (imports un-sorted)
```bash
ruff check backend --select I --fix
ruff format backend
```

### Ruff format --check failina
Dazniausios priezastys:
- Extra empty line at EOF (failas baigiasi dviem tuščiom eilutem)
- Du tusci tarpai tarp top-level statement'u
- Quote style mismatch (`'single'` vs `"double"`)
- CRLF line endings (Windows)

```bash
# Fix viskas viena komanda:
ruff format backend
ruff check backend --fix
```

### Pre-push patikra (PRIVALOMA pries git push)
CI vykdo 3 zingsnius; visi turi praeiti:

```bash
ruff check backend/
ruff format backend/ --check
# + pytest (CI job "Run tests")
```

**Pilna procedura** (Ubuntu/VM arba lokaliai su Python):
```bash
cd ~/VejaPRO   # arba worktree
source .venv/bin/activate
ruff check backend/
ruff format backend/ --check
PYTHONPATH=backend python -m pytest backend/tests -v --tb=short
```

Jei `ruff` nera PATH'e:
```bash
python -m ruff check backend
python -m ruff format backend
```

## Svarbios pastabos

- `ruff format` yra formatteris (kaip Black) ir yra grietztas del whitespace. Net jei kodas veikia, CI gali failinti.
- Repo naudoja Ruff formatting defaults + `quote-style = "double"` ir `line-length = 120` is `ruff.toml`.
- `known-first-party = ["app"]` — importai is `app.*` klasifikuojami kaip local.
- Jei negalite instaliuoti Ruff lokaliai (Windows), naudokite WSL arba standartini CPython is python.org.
