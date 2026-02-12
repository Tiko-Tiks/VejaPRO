# Prisidejimo gidas

Sis dokumentas apraso, kaip dirbti su VejaPRO kodu: nuo brancho iki deploy.

## Darbo eiga

```
1. Sukurk branch  ->  2. Kodink + testink  ->  3. Push + PR  ->  4. CI zalias  ->  5. Merge  ->  6. Auto-deploy
```

## 1. Branch kurimas

Visa darbas vyksta branchuose. Niekada nedaryk tiesioginio push i `main`.

```bash
git checkout main && git pull
git checkout -b <tipo>/<trumpas-aprasymas>
```

### Branch tipo prefiksai

| Prefiksas | Kada naudoti | Pavyzdys |
|-----------|-------------|----------|
| `feat/` | Naujas funkcionalumas | `feat/email-auto-reply` |
| `fix/` | Bug fix | `fix/naive-datetime-comparison` |
| `docs/` | Dokumentacija | `docs/infrastructure-cleanup` |
| `test/` | Tik testai | `test/finance-ledger-edge-cases` |
| `style/` | Formatavimas, lint | `style/ruff-format-all` |

## 2. Commit zinutes

Angliskai, conventional commit formatu:

```
<tipas>(<scope>): <trumpas aprasymas>

[nebutinas ilgesnis aprasymas]
```

Tipai: `feat`, `fix`, `docs`, `test`, `style`, `refactor`, `ci`, `chore`

Pavyzdziai:
- `feat(email): add CloudMailin webhook endpoint`
- `fix(tests): use uuid4 for provider_event_id`
- `docs: update INFRASTRUCTURE.md with rollback procedure`

## 3. Kodo stilius

- **Linteris:** ruff 0.15 (taisykles: E/W/F/I/B/UP, line-length: 120)
- **Lokaliai tikrinti:**
  ```bash
  C:/Users/Administrator/ruff.exe check backend/
  C:/Users/Administrator/ruff.exe format backend/ --check --diff
  ```
- **Automatinis formatavimas** (jei naudoji Claude Code): PostToolUse hook paleidzia ruff ant kiekvieno `.py` failo edito

## 4. Testavimas

Testai paleidziami **serveryje** per SSH (ne lokaliai):

```bash
ssh -i "C:/Users/Administrator/.ssh/vejapro_ed25519" administrator@10.10.50.178 \
  "cd /home/administrator/VejaPRO && \
   DATABASE_URL=sqlite:////tmp/veja_test.db ENVIRONMENT=test PYTHONPATH=backend \
   ENABLE_FINANCE_LEDGER=true ENABLE_MANUAL_PAYMENTS=true ENABLE_EMAIL_INTAKE=true \
   ENABLE_SCHEDULE_ENGINE=true ENABLE_CALENDAR=true \
   SUPABASE_URL=https://fake.supabase.co SUPABASE_KEY=fake TEST_AUTH_ROLE=ADMIN \
   python3 -m pytest backend/tests -v --tb=short \
   --override-ini='filterwarnings='"
```

### Testavimo reikalavimai

- Visi esami testai turi praeiti
- Naujas funkcionalumas reikalauja nauju testu
- Naudok `uuid.uuid4()` dinaminiam `provider_event_id`
- SQLite testams: `.replace(tzinfo=None)` datetime palyginimams

## 5. Feature flagai

Kuriant nauja moduli, reikia prideti feature flag:

1. **`backend/app/core/config.py`** — `enable_xxx: bool = Field(default=False, ...)`
2. **`.github/workflows/ci.yml`** — `ENABLE_XXX: "true"` (arba `"false"` jei neturi testu)
3. **`backend/.env.example`** — `ENABLE_XXX=false  # [default: false] Aprasymas`
4. **Dokumentacija** — `STATUS.md`, `VEJAPRO_TECHNINE_DOKUMENTACIJA_V2.md`, `API_ENDPOINTS_CATALOG.md`
5. **`CLAUDE.md`** — atnaujink flagu skaiciu ir key flags sarasa

Isijungto flago modulis turi grazinti **404** (ne 403) — del saugumo.

## 6. PR procesas

1. Push savo brancha: `git push -u origin <branch>`
2. Sukurk PR i `main` per GitHub
3. Palaukk kol CI praeis (ruff check -> ruff format -> pytest)
4. Merge metodas: **Squash and merge** (vienas svaresnis commit i main)
5. Po merge istrinamas remote branch

### PR checklist

- [ ] Visi testai praejo (CI zalias)
- [ ] Ruff lint + format clean
- [ ] Nauji feature flagai prideti i ci.yml
- [ ] Dokumentacija atnaujinta (jei aktualu)
- [ ] Jokiu `.env`, slaptazodziu ar PII kode

## 7. Deploy

Deploy vyksta **automatiskai** po merge i `main`:

- Serveris periodiskai (kas ~5 min) tikrina `origin/main`
- Jei randa nauju commitu: `git pull` + `systemctl restart vejapro`
- Health check: `https://vejapro.lt/health`

### Rankinis deploy (jei reikia greiciau)

```bash
ssh veja-vm "sudo systemctl start vejapro-update.service"
```

### Alembic migracijos (rankinis zingsnis)

Jei pridejote nauja migracija, serveryje reikia paleisti:

```bash
ssh veja-vm "cd /home/administrator/VejaPRO && \
  source /home/administrator/.venv/bin/activate && \
  cd backend && alembic upgrade head"
```

## Dokumentacijos atnaujinimo checklist

Kai kuriate nauja moduli/funkcija, atnaujinkite:

| Failas | Ka atnaujinti |
|--------|--------------|
| `STATUS.md` | Versijos numeris, metrikos, moduliu lentele |
| `backend/VEJAPRO_TECHNINE_DOKUMENTACIJA_V2.md` | Feature flags sarasas, nauja sekcija |
| `backend/API_ENDPOINTS_CATALOG.md` | Feature flags, nauji endpointai |
| `backend/.env.example` | Nauji env kintamieji su komentarais |
| `CLAUDE.md` | Flagu skaicius, testu skaicius, key flags |

## Naudingos nuorodos

- `INFRASTRUCTURE.md` — deploy runbook, rollback, troubleshooting
- `backend/VEJAPRO_KONSTITUCIJA_V2.md` — verslo taisykles (UZRAKINTA)
- `backend/API_ENDPOINTS_CATALOG.md` — visu 79+ endpointu katalogas
- `backend/docs/ADMIN_UI_V3.md` — admin UI architektura
