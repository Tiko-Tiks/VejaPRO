# Client UI V3 (Backend-driven, LOCKED)

Paskutinis atnaujinimas: **2026-02-11**

Šis dokumentas aprašo Client UI V3: backend-driven view modelius, hash routerį, CTA mapping ir endpoint kontraktus. Pilna specifikacija – planas „Client UI V3 — Backend-driven planas (FINAL / LOCKED)“.

---

## Maršrutai (Frontend)

Vienas failas `backend/app/static/client.html`. Hash routeris:

| Hash        | Ekranas          | API |
|------------|------------------|-----|
| `#/`       | Dashboard        | `GET /api/v1/client/dashboard` |
| `#/projects` | Mano projektai | Duomenys iš dashboard arba `GET /api/v1/client/projects` |
| `#/projects/{id}` | Projekto detalės | `GET /api/v1/client/projects/{id}/view` |
| `#/estimate` | Įvertinimo vedlys | `GET /api/v1/client/estimate/rules` + analyze/price/submit |
| `#/services` | Papildomos paslaugos | `GET /api/v1/client/services/catalog`, `POST .../request` |
| `#/help`   | Pagalba          | Statinis tekstas |

Autentifikacija: JWT (Bearer). Token saugomas `localStorage` (vejapro_client_token). Po prisijungimo UI veikia tik per `current_user.id`; projektų prieiga – 404, jei nėra prieigos (ne 403).

---

## CTA mapping (Backend helper `compute_next_step_and_actions`)

| Statusas   | Sąlyga | primary_action |
|------------|--------|----------------|
| DRAFT      | quote_pending=true | view_quote_status |
| DRAFT      | quote_approved + deposit_due | pay_deposit |
| PAID       | contract_signed=false | sign_contract |
| PAID       | contract_signed=true | view_schedule |
| CERTIFIED  | final_due=true | pay_final |
| CERTIFIED  | final_paid + confirmation_pending | confirm_acceptance |
| ACTIVE     | — | order_maintenance |

UI niekada nekviečia `POST /api/v1/transition-status`. Veiksmai kviečiami per **action endpoints**:

- `POST /api/v1/client/actions/pay-deposit`
- `POST /api/v1/client/actions/sign-contract`
- `POST /api/v1/client/actions/pay-final`
- `POST /api/v1/client/actions/confirm-acceptance`
- `POST /api/v1/client/actions/order-service`

Kūnas: `{ "project_id": "uuid" }`.

---

## Endpoint kontraktai (santrauka)

### Dashboard
- **GET /api/v1/client/dashboard**  
  Grąžina: `action_required[]`, `projects[]`, `upsell_cards[]`, `feature_flags`.  
  Be PII (7.9).

### Projekto view
- **GET /api/v1/client/projects/{id}/view**  
  Grąžina: `status`, `status_hint`, `next_step_text`, `primary_action`, `secondary_actions[]` (max 2), `documents[]` (type iš enum 7.8), `timeline[]`, `payments_summary`, `addons_allowed`.  
  Prieiga: 404 jei klientas neturi prieigos (10.1).

### Įvertinimas
- **GET /api/v1/client/estimate/rules** – `rules_version`, `base_rates`, `addons[]`, `disclaimer`, `confidence_messages`
- **POST /api/v1/client/estimate/analyze** – `area_m2`, `photo_file_ids[]` → `ai_complexity`, `base_range`, `confidence_bucket`
- **POST /api/v1/client/estimate/price** – `rules_version`, `base_range`, `addons_selected[]` → 409 jei pasenęs (7.4)
- **POST /api/v1/client/estimate/submit** – sukuria DRAFT projektą, `client_info.estimate`, `quote_pending=true`; 409 jei rules_version pasenęs

### Paslaugos
- **GET /api/v1/client/services/catalog** – deterministinis, `catalog_version`, 3–6 kortelės (7.6)
- **POST /api/v1/client/services/request** – sukuria `service_requests` įrašą; PAID+ projektas = visada atskiras request

### Dokumentų tipai (7.8)
`PRELIM_QUOTE`, `INVOICE_DEPOSIT`, `CONTRACT`, `SCHEDULE`, `CERTIFICATE`, `INVOICE_FINAL`, `WARRANTY`.

### Service request statusai (7.7)
`NEW` → `IN_REVIEW` → `QUOTED` → `SCHEDULED` → `DONE` | `CLOSED`.

---

## Failai

- **Backend:** `app/api/v1/client_views.py`, `app/services/client_view_service.py`, `app/services/estimate_rules.py`, `app/schemas/client_views.py`
- **Modelis:** `app/models/project.py` – `ServiceRequest`; migracija `20260211_000017_service_requests.py`
- **Frontend:** `app/static/client.html` (hash routeris + 5 view: dashboard, projects, project view, estimate, services, help)
