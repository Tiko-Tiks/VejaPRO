# Admin UI V3 (Sidebar + Shared Design System + Operator Workflow)

Paskutinis atnaujinimas: **2026-02-11**

Sis dokumentas apraso Admin UI V3 redesign: bendrus asset'us (CSS/JS), sidebar navigacija, Klientu moduli, `/admin/projects` migracija ir **V3.3 Operator Workflow** (dashboard su triage, SSE, filter chips, Summary tab).

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

### Faze D: Operator Workflow (V3.3, 2026-02-11)
Atlikta:
- **Dashboard** (`/admin`):
  - Hero: 4 stat kortelės (Klientai su veiksmu, Laukia patvirtinimo, Nepavykę pranešimai, Nauji skambučiai)
  - Triage: horizontalūs kortelės (Trello-style), urgency pills (high/medium/low), vienas PRIMARY mygtukas
  - AI summary pill (jei `ENABLE_AI_SUMMARY=true`)
  - SSE real-time triage atnaujinimai
- **Backend:**
  - `GET /api/v1/admin/dashboard` — hero, triage, ai_summary, customers_preview
  - `GET /api/v1/admin/dashboard/sse` — SSE stream triage atnaujinimams (5s interval)
  - `backend/app/api/v1/admin_dashboard.py`
  - `admin_read_models.py::build_dashboard_view`
- **Klientai:** filter chips (Laukia patvirtinimo, Nepavykę pranešimai), urgency eilutės (row-urgency-high/medium/low), tooltip „Kodėl urgency“
- **Kliento profilis:** Summary tab pirmas (su AI next action pill + PRIMARY mygtuku)
- **Sidebar:** 240px, #1a1a2e fonas, token generatorius collapsible apačioje

Liko (veliau):
- Kiti admin puslapiai: calls, calendar, audit, margins, finance, ai-monitor pilnai migruoti.
- SSE targeted update kitiems puslapiams (pvz. naujas payment → eilutė highlight).

---

## Shared asset'ai

### CSS: `backend/app/static/admin-shared.css`
Vienas saltinis dizainui:
- design tokens: `--sidebar-w: 240px`, `--sidebar-bg: #1a1a2e`, `--bg: #fafaf9`.
- komponentai: `.card`, `.data-table`, `.pill*`, `.btn*`, `.modal*`, `.form-grid`, `.tabs`.
- **V3.3:** `.row-urgency-high/medium/low`, `.triage-card`, `.triage-container`, `.filter-chips`, `.ai-summary-pill`, `.sidebar-token`.
- accessibility: `:focus-visible`, `.sr-only`.
- responsive: sidebar overlay mobile rezime, table -> card layout, 48px touch targets.

### JS: `backend/app/static/admin-shared.js`
- `Auth`:
  - `STORAGE_KEY = "vejapro_admin_token"`
  - `generate()` tik rankiniu budu (mygtukas). Niekada negeneruoti tyliu budu.
- `authFetch(url, options)`:
  - automatinis `Authorization: Bearer ...`
  - error strategija: 401 rodo token kortele; 403/404 toast; 429 toast; 5xx toast + logina tik status/req-id (ne body).
- UI helperiai: `escapeHtml`, `formatDate`, `formatCurrency`, `showToast`, `copyToClipboard`, `maskEmail`, `maskPhone`.
- Sidebar: `sidebarHTML(activePage)` + `initSidebar()`.
- **V3.3:** `startDashboardSSE()`, `stopDashboardSSE()` — EventSource į `/admin/dashboard/sse?token=`.
- **V3.3:** `quickAction(type, projectId, clientKey)` — one-click workflow redirect.

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
    - `/static/admin-shared.css?v=3.3`
    - `/static/admin-shared.js?v=3.3`
    - `/static/admin-projects.js?v=3.1`
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
- `/admin` atsidaro, dashboard rodo hero + triage + klientų lentelę.
- Token flow: be token -> rodo noTokenHint, sidebar token collapsible apačioje.
- `/admin/customers` rodo sąrašą, filter chips veikia (Laukia patvirtinimo, Nepavykę pranešimai).
- Kliento profilis: Summary tab pirmas, tabs kraunasi, resend/retry rodo remaining/reset_at.
- `/admin/projects` list load veikia, rankinis mokėjimas veikia, admin-confirm praso reason.
- SSE: dashboard SSE jungiasi (`/admin/dashboard/sse?token=`), triage atnaujinimai kas 5s.
