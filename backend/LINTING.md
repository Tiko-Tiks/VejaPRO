# Linting / Formatting (CI)

CI blocks merges on formatting or lint mismatches.

What CI runs:

```bash
ruff check backend/
ruff format backend/ --check --diff
```

Notes:

- `ruff format` is a formatter (like Black) and is strict about whitespace. It will fail CI even if code "works".
- Migrations are formatted too: `backend/app/migrations/versions/*.py`.
  They may be ignored by `ruff check`, but they are still checked by `ruff format`.
- The repo uses Ruff formatting defaults plus `quote-style = "double"` and `line-length = 120` from `ruff.toml`.

Common causes of `ruff format --check` failures:

- Extra empty line at EOF (file ends with two newlines). Ruff will remove the extra blank line.
- Two blank lines between top-level statements (Ruff usually keeps a single blank line).
- Quote style mismatch (`'single quotes'` vs `"double quotes"`).
- Accidental CRLF line endings on Windows.

Quick pre-push sanity checks:

```bash
git diff --check
```

If you have Ruff locally:

```bash
ruff format backend/
ruff check backend/ --fix
```

If you can't install Ruff locally (common on Windows with an unsupported Python build), use one of:

- WSL (Ubuntu) and run Ruff there
- A standard CPython from python.org (so `pip install ruff` works)
