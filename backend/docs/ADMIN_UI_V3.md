# Admin UI V3 (Sidebar + Shared Design System)

Paskutinis atnaujinimas: **2026-02-10**

Sis dokumentas apraso Admin UI V3 redesign implementacija: bendrus asset'us (CSS/JS), sidebar navigacija, Klientu moduli ir `/admin/projects` migracija i bendra dizaino sistema.

---

## Tikslas

Problemos pries V3:
- Kiekvienas admin puslapis turejo didele inline CSS dali (dubliavimas).
- Nesuvienodintos spalvos ir komponentai.
- Horizontalus meniu netinkamas 8+ puslapiams.
- Nebuvo greito kliento vaizdo (operatorius nemate bendros kliento bukles).
- `projects.py` buvo monolitas, prireike plonesniu admin routeriu.

Tikslas:
- Vienodas admin puslapiu dizainas, sidebar meniu.
- Naujas Klientu modulis (sarasas + profilis su tabs).
- Workflow veiksmai (ne "set status").
- PII politika: Admin UI nerodo raw PII (email/phone).

---

## Fazes (scope)

### Faze A: Pagrindas (shared UI)
Atlikta:
- `backend/app/static/admin-shared.css` (design tokens + komponentai).
- `backend/app/static/admin-shared.js` (Auth, `authFetch`, utils, sidebar).
- `backend/app/static/admin.html` (dashboard su sidebar).

### Faze B: Klientu modulis
Atlikta:
- UI:
  - `backend/app/static/customers.html` (klientu lentele).
  - `backend/app/static/customer-profile.html` (profilis su tabs).
- Backend:
  - `backend/app/api/v1/admin_customers.py`:
    - `GET /api/v1/admin/customers`
    - `GET /api/v1/admin/customers/stats`
    - `GET /api/v1/admin/customers/{client_key}/profile`
  - `backend/app/services/admin_read_models.py`:
    - derived `client_key` + confidence
    - agregacijos ir view-model builderiai (ploni routeriai)
  - `backend/app/api/v1/admin_project_details.py`:
    - `GET /api/v1/admin/projects/{id}/payments`
    - `GET /api/v1/admin/projects/{id}/confirmations`
    - `POST /api/v1/admin/projects/{id}/confirmations/resend`
    - `GET /api/v1/admin/projects/{id}/notifications`
    - `POST /api/v1/admin/notifications/{id}/retry`

### Faze C: Esamu puslapiu migracija
Atlikta (pradzia):
- `/admin/projects` migracija i V3:
  - `backend/app/static/projects.html` (V3 layout, be didelio inline CSS).
  - `backend/app/static/admin-projects.js` (page logika, modals, workflow veiksmai, deep-link'ai).

Liko (veliau):
- Kiti admin puslapiai: calls, calendar, audit, margins, finance, ai-monitor.

---

## Shared asset'ai

### CSS: `backend/app/static/admin-shared.css`
Vienas saltinis dizainui:
- design tokens (spalvos, radius, z-index, layout).
- komponentai: `.card`, `.data-table`, `.pill*`, `.btn*`, `.modal*`, `.form-grid`, `.tabs`.
- accessibility: `:focus-visible`, `.sr-only`.
- responsive: sidebar overlay mobile rezime, table -> card layout.

### JS: `backend/app/static/admin-shared.js`
- `Auth`:
  - `STORAGE_KEY = "vejapro_admin_token"`
  - `generate()` tik rankiniu budu (mygtukas). Niekada negeneruoti tyliu budu.
- `authFetch(url, options)`:
  - automatinis `Authorization: Bearer ...`
  - error strategija: 401 rodo token kortele; 403/404 toast; 429 toast; 5xx toast + logina tik status/req-id (ne body).
- UI helperiai: `escapeHtml`, `formatDate`, `formatCurrency`, `showToast`, `copyToClipboard`, `maskEmail`, `maskPhone`.
- Sidebar: `sidebarHTML(activePage)` + `initSidebar()`.

---

## Klientu modulis (Faze B)

### Derived client_key
`client_key` yra derived identifikatorius, nera rasomas i DB atgal.
Tikslas: sugrupuoti projektus pagal klienta be raw PII rodymo UI.

Kodas:
- `backend/app/services/admin_read_models.py:derive_client_key()`

UI rodo:
- maskuota kontakta (pvz. `j***@v***.lt / +3706*****12`)
- `client_key_confidence` (HIGH/MEDIUM/LOW) perspėjimui.

### PII taisykle (MVP)
- Admin UI neturi endpointo, kuris grazina raw email/phone klientu modulyje.
- UI papildomai maskuoja PII detaliu modale (defense-in-depth).

---

## Workflow-only veiksmai (no "set status")

Pagrindinis principas: statusas keiciamas tik per workflow komandas / `transition-status`.

Svarbu:
- `record_final_payment` NEaktyvuoja projekto tiesiogiai; ACTIVE tik po patvirtinimo.
- Admin override aktyvacija: `POST /api/v1/admin/projects/{id}/admin-confirm` reikalauja `{ "reason": "..." }`.

---

## `/admin/projects` (Faze C startas)

UI failai:
- `backend/app/static/projects.html`:
  - naudoja shared CSS/JS:
    - `/static/admin-shared.css?v=3.1`
    - `/static/admin-shared.js?v=3.1`
    - `/static/admin-projects.js?v=3.0`
  - sidebar navigacija, token kortele, filtrai, lentele, modals.
- `backend/app/static/admin-projects.js`:
  - list/pagination
  - modals: details, client token, manual payment, stripe link, assign
  - deep-link'ai:
    - `#manual-deposit-<uuid>`
    - `#manual-final-<uuid>`
    - `#<uuid>` (atidaro detales)

---

## Verifikacija

### CI / Lokalūs testai (Ubuntu)
CI modelis: `ruff` -> DB paruosimas -> `pytest` (in-process).

Pavyzdys (kaip GH Actions):
```bash
cd /home/administrator/VejaPRO
source .venv/bin/activate
export PYTHONPATH=backend
export DATABASE_URL=sqlite:////tmp/veja_api_test.db

python - <<'PY'
from app.core.dependencies import engine
from app.models.project import Base
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
print("db ready")
PY

ruff check backend/ --output-format=github
ruff format backend/ --check --diff
pytest backend/tests -v --tb=short
```

### Smoke checklist (Admin UI)
- `/admin` atsidaro, sidebar veikia.
- Token flow: be token -> 401 -> rodo token kortele (ne auto-generate).
- `/admin/customers` rodo sarasa (default: attention-only), veikia "Rodyti visus".
- Kliento profilis atsidaro, tabs kraunasi, resend/retry rodo remaining/reset_at.
- `/admin/projects` list load veikia, rankinis mokejimas veikia, admin-confirm praso reason.
