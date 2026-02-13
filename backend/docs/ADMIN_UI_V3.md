# Admin UI V3 (Sidebar + Shared Design System + Operator Workflow)

Paskutinis atnaujinimas: **2026-02-13** (V6.0)

Sis dokumentas apraso Admin UI redesign: bendrus asset'us (CSS/JS), sidebar navigacija, Klientu moduli, `/admin/projects` migracija, **V3.3 Operator Workflow** (dashboard su triage, SSE, filter chips, Summary tab), **V5.3 funkcionalumo fix** (auth, form auto-styling, LT vertimai) ir **V6.0 SaaS redesign** (light/dark tema, darbo eilė, profesionalus stilius).

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
Atlikta (Diena 1 – Projektai, 2026-02-11):
- `/admin/projects` V3 pilnas:
  - **Backend (LOCK 1.1):** `GET /api/v1/admin/projects` lieka nepakeistas. Naujas `GET /api/v1/admin/projects/view` — ProjectsViewModel (items su next_best_action, attention_flags, stuck_reason, last_activity, client_masked, cursor, as_of, view_version). Naujas `GET /api/v1/admin/projects/mini-triage` (LOCK 1.6).
  - **Frontend:** `projects.html` — filter chips (statusai + „Laukiantys veiksmo" default), mini triage virš lentelės, AI summary pill, lentelė su row-urgency-*, PRIMARY mygtukas per next_best_action, SSE startDashboardSSE.
  - **admin-projects.js:** fetchProjects naudoja `/admin/projects/view`, fetchMiniTriage, quickAction (assign_expert, certify_project), deep links (#assign-expert-{id}, #certify-{id}).
  - **admin_read_models.py:** `build_projects_view`, `build_projects_mini_triage`, `_next_best_action_for_project`.

### Faze D: Operator Workflow (V3.3, 2026-02-11)
Atlikta:
- **Dashboard** (`/admin`):
  - Hero: 4 stat kortelės (Reikia veiksmo, Laukia patvirtinimo, Nepavykę pranešimai, Nauji skambučiai)
  - **V6.0:** Darbo eilė lentelė (vietoj Trello-style triage kortelių), prioriteto taškai (high/medium/low), Aktyvūs/Archyvas tabs
  - SSE real-time triage atnaujinimai (per `renderTriage` wrapper)
- **Backend:**
  - `GET /api/v1/admin/dashboard` — hero, triage, ai_summary, customers_preview
  - `GET /api/v1/admin/dashboard/sse` — SSE stream triage atnaujinimams (5s interval)
  - `backend/app/api/v1/admin_dashboard.py`
  - `admin_read_models.py::build_dashboard_view`
- **Klientai:** filter chips (Laukia patvirtinimo, Nepavykę pranešimai), urgency eilutės (row-urgency-high/medium/low), tooltip „Kodėl urgency"
- **Kliento profilis:** Summary tab pirmas (su AI next action pill + PRIMARY mygtuku)
- **Sidebar:** 240px, #1a1a2e fonas, token generatorius collapsible apačioje

**Diena 4 (2026-02-11) — Finansai ir AI:**
- **Finansai** (`/admin/finance`): sidebar token, mini triage (laukiantys mokėjimai), AI summary pill, SSE metrics kortelės viršuje. `GET /admin/finance/view`, `GET /admin/finance/mini-triage`. quickAction (record_deposit, record_final).
- **AI** (`/admin/ai`): sidebar token, Global Attention (žemi confidence), AI summary „Patikrinti N klaidų". `GET /admin/ai/view`. renderMiniTriage reusable JS.

**Diena 5–6 (2026-02-11) — Token unifikacija, Global search:**
- Token perkeltas į sidebar visur (audit, calls, calendar, margins, projects).
- `GET /admin/search?q=` — globali paieška (projektai, skambučiai). Sidebar viršuje input, Ctrl+K.

**Diena 7 (2026-02-12) - Dev-friendly auth modelis (dual path):**
- Naujas puslapis: `GET /login` (`backend/app/static/login.html` + `backend/app/static/login.js`).
- Login JS yra atskirame faile (be inline script) ir naudoja griezta CSP (`/login` route header'iai).
- Supabase sesija saugoma tik `sessionStorage["vejapro_supabase_session"]` (be localStorage persistencijos).
- Dev token kelias nelauzomas: `GET /api/v1/admin/token` + `localStorage["vejapro_admin_token"]`.
- Naujas endpointas: `POST /api/v1/auth/refresh` (single-flight refresh frontend'e, rotation-safe).
- Token korteleje: secret input + "Gen." mygtukas (su `X-Admin-Token-Secret` header) ir "Prisijungti" mygtukas.
- Sidebar "Atsijungti" rodomas tik Supabase sesijos rezime.

### V5.3: Funkcionalumo fix (2026-02-12)

**Auth flow:**
- `Auth.generate(secret)` dabar priima secret parametra ir siucia `X-Admin-Token-Secret` header (anksciau visada gaudavo 404).
- Token card'e atsirado secret input laukelis + "Prisijungti" mygtukas (nuoroda i `/login`).
- 401 toast pranesimas pakeistas: "Prisijunkite per /login arba sugeneruokite zetoną."
- Login page (`login.js`) aptinka kai Supabase credentials neinjektuoti ir rodo pranesima.

**Auth checks visuose puslapiuose:**
- Dashboard ir Customers: `loadDashboard()` / `loadCustomers()` kviečiami be sąlygos (fix amžino spinnerio).
- Calls, Calendar, Audit, Finance, Margins, AI Monitor: pridėti auth checks kurie rodo aiškų pranešimą vietoj toast'ų lavinos ar amžino spinnerio.

**CSS auto-styling (bare form elements):**
- Pridėtos CSS taisyklės kurios automatiškai stilizuoja `<input>`, `<select>`, `<textarea>` elementus be `.form-input`/`.form-select` klasių admin konteineriuose (`.section`, `.form-grid`, `.filters`, `.modal-body`, `.export-row`, `.views-row`, `.card >`).
- Vienu CSS pakeitimu sutvarkyta ~50 nestilingų laukelių calls/calendar/audit puslapiuose.

**Kalendorius — supaprastinimas:**
- Advanced sections ("Planavimo įrankiai", "Hold įrankiai", "Perplanavimas") suvynioti i `<details>/<summary>` (sutraukiami pagal default).
- Visos etiketės išverstos i lietuvių kalbą (UUID → Neprivaloma, resource_id → Darbuotojas, lock_level → Užrakinimo lygis, ir t.t.).

**Vertimai (LT):**
- Projektų filter chips: DRAFT → Juodraštis, PAID → Apmokėtas, SCHEDULED → Suplanuotas, PENDING_EXPERT → Laukia eksperto, CERTIFIED → Sertifikuotas, ACTIVE → Aktyvus.
- Audito select'ai: entity_type/actor_type options lietuviškai (display labels, values angliški API).
- Maržų placeholder: "pvz., LAWN_INSTALL" → "pvz., Vejos įrengimas".

**Graceful empty states:**
- Finance SSE ir AI Monitor: rodo pranešimą "Prisijunkite..." kai nėra tokeno, vietoj "Atjungta" ar brūkšnių.
- Margins: previewCalc auksinis baras paslėptas kai tuščias (`display:none` pradžioje).

Liko (veliau):
- SSE targeted update kitiems puslapiams (pvz. naujas payment → eilutė highlight).

### V6.0: SaaS Redesign — Light/Dark tema, darbo eilė (2026-02-13)

**Kontekstas:** Ankstesnis dizainas buvo orientuotas į grožį (dark obsidian + amber glow + dekoracijos), bet operatoriui nepatogu dirbti su dideliu kiekiu duomenų. V6.0 perjungia į profesionalų SaaS stilių (Stripe/Linear/Notion tipo).

**Light/Dark tema:**
- `Theme` objektas `admin-shared.js`: `get()`, `set()`, `toggle()`, `init()`, saugoma `localStorage["vejapro_theme"]`.
- Default: light tema. Dark tema aktyvuojama per toggle mygtuką sidebar'e (☀️/🌙 ikona).
- FOUC prevencija: inline `<script>` prieš `</head>` kiekviename admin HTML faile skaito localStorage ir nustato `data-theme` prieš pirmą renderį.
- CSS struktūra: `:root` turi tik temos-nepriklausomus kintamuosius (radius, z-index, transitions, fonts, spacing, sidebar spalvos). `:root, [data-theme="light"]` turi light spalvas. `[data-theme="dark"]` turi dark spalvas.
- Sidebar visada tamsus (`--sidebar-bg: #1a1a2e`) abiejose temose.

**Dashboard redesign:**
- Triage kortelės (horizontalios Trello-style) pakeistos **darbo eilės lentele** su prioriteto taškais (🔴 high, 🟡 medium, ⚪ low).
- Stulpeliai: Prioritetas | Klientas | Problema | Statusas | Paskutinis veiksmas | Veiksmas (mygtukas).
- `renderWorkQueue(triage, customersPreview)` — sujungia triage + klientus su attention flags, rūšiuoja pagal urgency.
- **Aktyvūs/Archyvas tabs**: Archyvas lazy-load'ina klientus be attention flags.
- Stats: 4 kompaktiškos kortelės (Reikia veiksmo, Laukia patvirtinimo, Nepavykę pranešimai, Nauji skambučiai).
- `renderTriage` wrapper SSE suderinamumui.

**SaaS stilistika (pašalinta):**
- `body::before` (noise SVG filter + radial gradient).
- `card::after`, `card-stat::before/::after`, `table-container::after`, `triage-card::after` (glass pseudo-elementai).
- `.sidebar::before` gradient wash.
- Glow shadows (`--glow-accent`, `--glow-error` → `none` light temoje).
- Gradient mygtukai → solidūs (`--accent` fonas).

**Nauji CSS komponentai:**
- `.theme-toggle` — tema perjungimo mygtukas sidebar'e.
- `.priority-dot` (`.high`, `.medium`, `.low`) — darbo eilės prioriteto indikatoriai.
- `.archive-row` — pritemdytos archyvo eilutės.
- Zebra striping: `.data-table tbody tr:nth-child(even)`.
- Theme-aware scrollbar: `--scrollbar-thumb`, `--scrollbar-thumb-hover`.

**Cache-bust:** `?v=6.0` visuose 11 admin HTML failų (CSS + JS).

---

## Shared asset'ai

### CSS: `backend/app/static/admin-shared.css`
Vienas saltinis dizainui (V6.0):
- **Temos sistema:** `:root` (shared tokens) + `:root, [data-theme="light"]` (light) + `[data-theme="dark"]` (dark).
- Sidebar visada tamsus: `--sidebar-bg: #1a1a2e`, `--sidebar-ink`, `--sidebar-hover` `:root` bloke.
- komponentai: `.card`, `.data-table`, `.pill*`, `.btn*`, `.modal*`, `.form-grid`, `.tabs`.
- **V3.3:** `.row-urgency-high/medium/low`, `.triage-card`, `.triage-container`, `.filter-chips`, `.ai-summary-pill`, `.sidebar-token`.
- **V5.1:** `.stat-card`, `.stat-label`, `.stat-value`, `.stat-subtext`, `.section`, `.section-title`, `.section-subtitle`, `.content-column`, `.value-green/red/blue`, `.empty-row`.
- **V5.3:** Bare form auto-styling, `<details>` stilizavimas.
- **V6.0:** `.theme-toggle`, `.priority-dot`, `.archive-row`, zebra striping, theme-aware scrollbar. Pašalintos visos dekoracijos (noise, glow, glass).
- accessibility: `:focus-visible`, `.sr-only`.
- responsive: sidebar overlay mobile rezime, table -> card layout, 48px touch targets.
- cache-busting: visi admin HTML failai naudoja `?v=6.0` (CSS + JS).

### JS: `backend/app/static/admin-shared.js`
- **`Theme`** (V6.0):
  - `KEY = "vejapro_theme"`
  - `get()` → localStorage arba "light" default
  - `set(t)` → localStorage + `document.documentElement.dataset.theme`
  - `toggle()` → dark↔light
  - `init()` → kviečiamas iš karto failo viršuje (FOUC prevencija)
  - Toggle mygtukas injektuojamas `initSidebar()` metu prieš `.sidebar-footer`
- `Auth`:
  - `STORAGE_KEY = "vejapro_admin_token"`
  - `SUPABASE_SESSION_KEY = "vejapro_supabase_session"`
  - `getToken()` pirmiausia skaito sessionStorage (Supabase), fallback i localStorage (dev token)
  - `refreshIfNeeded()` -> `POST /api/v1/auth/refresh` su single-flight
  - `logout()` valo tik Supabase sesija ir redirectina i `/login`
  - `generate(secret)` priima secret parametra, siucia `X-Admin-Token-Secret` header. Tik rankiniu budu (mygtukas).
- `authFetch(url, options)`:
  - automatinis `Authorization: Bearer ...`
  - error strategija: 401 rodo "Prisijunkite per /login arba sugeneruokite zetoną."; 403/404 toast; 429 toast; 5xx toast + logina tik status/req-id (ne body).
- `initTokenCard()`: generuoja token card turinį su "Prisijungti" mygtuku + secret input + "Gen." mygtuku.
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
    - `/static/admin-shared.css?v=6.0`
    - `/static/admin-shared.js?v=6.0`
    - `/static/admin-projects.js?v=6.0`
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

### Smoke checklist (Admin UI V6.0)
- **Tema:** Toggle mygtukas sidebar'e (☀️/🌙) perjungia dark↔light, išsaugoma per reload.
- **Light mode:** šviesus fonas, aiškios spalvos, geras kontrastas, profesionalus stilius.
- **Dark mode:** tamsūs paviršiai, accent spalvos matomos, sidebar nesikeičia.
- **FOUC:** Puslapio užkrovimas nerodo trumpo "balto blyksnio" dark mode'e.
- `/login` — rodo Supabase-not-configured klaida jei credentials neinjektuoti.
- `/admin` be tokeno — rodo "Sugeneruokite žetoną" hint'ą (ne spinner'į).
- `/admin` su tokenu — dashboard rodo 4 stat kortelės + darbo eilė lentelė su prioriteto taškais.
- **Darbo eilė:** rodo TIK veiksmus kuriuos reikia atlikti, rūšiuota pagal prioritetą (🔴→🟡→⚪).
- **Archyvas tab:** rodo baigtus procesus (klientus be attention flags) atskirai.
- Token card: "Prisijungti" mygtukas + secret input + "Gen." mygtukas. Gen. su secret sugeneruoja tokeną.
- Visi puslapiai be tokeno — rodo aiškų pranešimą "Prisijunkite...", ne toast'ų laviną.
- `/admin/projects` — filter chips lietuviškai (Juodraštis, Apmokėtas, Suplanuotas...).
- `/admin/calendar` — advanced sections sutraukiami (`<details>`), etiketės lietuviškai.
- `/admin/audit` — select options lietuviškai (Projektas, Klientas, Rangovas...).
- `/admin/calls`, `/admin/calendar`, `/admin/audit` — visi form input'ai stilingi (ne balti naršyklės default'ai).
- `/admin/margins` — placeholder "pvz., Vejos įrengimas", previewCalc nerodomas tuščias.
- `/admin/finance` — be tokeno rodo pranešimą, ne "Atjungta".
- `/admin/ai` — be tokeno rodo pranešimą, ne brūkšnius.
- SSE: dashboard SSE jungiasi (`/admin/dashboard/sse?token=`), triage atnaujinimai kas 5s.
- `/admin/customers` rodo sąrašą, filter chips veikia.
- Kliento profilis: Summary tab pirmas, tabs kraunasi.
- Mobile: hamburger veikia, sidebar responsive.
- **Nėra dekoracinių efektų:** noise, glow, glass shadows pašalinti abiejose temose.
