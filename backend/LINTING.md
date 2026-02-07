# Linting / Formatting (CI)

CI blocks merges on formatting or lint mismatches.

What CI runs:

```bash
ruff check backend/
ruff format backend/ --check --diff
```

Common causes of `ruff format --check` failures:

- Extra empty line at EOF (file ends with two newlines). Ruff will remove the extra blank line.
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

