# PROJECT_CONTEXT

Trumpas projekto kontekstas ir kur rasti pilna specifikacija.

## Projekto esme
VejaPRO yra projektu valdymo ir sertifikavimo sistema. Pagrindinis srautas:
- Kliento projektas kuriamas -> vyksta apmokejimas -> planavimas -> eksperto patikra -> sertifikavimas -> aktyvus projektas.
- Visi statusai ir leidziami perejimai apibrezti dokumentacijoje.

## Pagrindiniai moduliai
- Projektų API (sukūrimas, peržiūra, statusų perėjimai).
- Audit log (privalomas visoms kritinėms veiksmams).
- Mokėjimai (Stripe + grynieji) + webhooks / rankinis cash patvirtinimas (payments-first doktrina).
- SMS (Twilio) ir Email patvirtinimai (`client_confirmations` lentelė su `channel` stulpeliu: sms, email, whatsapp).
- Evidence upload + sertifikavimo workflow + nuotraukų optimizavimas (Pillow: thumbnail WebP, medium WebP).
- Marketing/Gallery modulis (priklausomai nuo feature flag) su blur-up placeholder ir responsive images.
- Admin API ir Admin UI (projektai, auditas, maržos, skambučiai, kalendorius).
- Call Assistant — skambučių užklausų priėmimas per landing page formą.
- Email Intake (Unified Client Card) — anketa → pasiūlymo siuntimas su .ics → accept/reject per email nuorodą.
- Schedule Engine — RESCHEDULE preview/confirm, HOLD rezervacijos (Voice/Chat), daily batch approve.
- Voice webhook (Twilio) — automatinis laiko pasiūlymas su HELD + patvirtinimas/atšaukimas.
- Chat webhook + web chat widget (`/chat`) — pokalbio HELD pasiūlymo srautas.
- Notification outbox — asinchroninė SMS/email/WhatsApp pranešimų eilė su idempotencija ir retry.
- Hold expiry worker — periodinis HELD rezervacijų valymas.
- Finance modulis — išlaidų/pajamų knyga (ledger), dokumentų upload su SHA-256 dedup, AI ekstrakcija, vendor taisyklės, Quick Payment.
- Klientų portalas (`/client`) — projekto eigos peržiūra, rinkodaros sutikimas.
- Rangovo portalas (`/contractor`) — priskirtų projektų valdymas.
- Eksperto portalas (`/expert`) — sertifikavimo workflow, checklist, evidence.
- Galerija (`/gallery`) — viešoji projektų galerija su before/after nuotraukomis.

## Dokumentacija (pilna)
- `backend/VEJAPRO_KONSTITUCIJA_V2.md` — verslo logikos specifikacija (konsoliduota V1.3+V1.4)
- `backend/VEJAPRO_TECHNINE_DOKUMENTACIJA_V2.md` — techninė dokumentacija (konsoliduota V1.5+V1.5.1)
- `backend/API_ENDPOINTS_CATALOG.md` — pilnas API endpointu katalogas
- `backend/README.md` — developer quickstart ir architektura
- `backend/CONTRACTOR_EXPERT_PORTALS.md` — rangovo/eksperto portalų dokumentacija
- `backend/GALLERY_DOCUMENTATION.md` — galerijos modulio dokumentacija
- `backend/SCHEDULE_ENGINE_V1_SPEC.md` — planavimo masinos logika
- `SYSTEM_CONTEXT.md` — infrastruktūros ir deploy dokumentacija
- `backend/docs/archive/` — istoriniai dokumentai (auditai, deployment notes)

## Feature flags
Pilnas sarasas su paaiskinimai: `backend/.env.example` ir `backend/app/core/config.py::Settings`.

## Lokalizacija (i18n)
- Visa web sąsaja yra **lietuvių kalba** — pilnai sulietuvinti visi **11 HTML failų** (`lang="lt"`).
- ~**70 backend API klaidų pranešimų** išversti į lietuvių kalbą (`projects.py`, `assistant.py`, `schedule.py`, `transition_service.py`).
- Frontend JS pranešimai (loading, klaidos, būsenos, patvirtinimai) — lietuviškai (`projects.html`, `admin.html`, `calendar.html`, `contractor.html`, `audit.html`, `margins.html` ir kt.).
- Naudojami teisingi diakritikai: ą, č, ę, ė, į, š, ų, ū, ž.
- Datų formatavimas: `flatpickr` su LT locale, 24h formatas, pirmadienis savaitės pradžia.

## Testai
Testu instrukcijos: `backend/README.md` (1.2 sekcija).

## Portalų sąrašas

| Kelias | Failas | Paskirtis | Prieiga | Mobilus |
|--------|--------|-----------|---------|--------|
| `/` | `landing.html` | Viešas pradinis puslapis, užklausos forma | Vieša | ✓ |
| `/gallery` | `gallery.html` | Viešoji projektų galerija | Vieša | ✓ |
| `/chat` | `chat.html` | Web chat widget (testavimo UI) | Vieša | ✓ |
| `/client` | `client.html` | Klientų portalas (projekto eiga) | JWT | ✓ |
| `/contractor` | `contractor.html` | Rangovo portalas (priskirti projektai) | JWT | ✓ |
| `/expert` | `expert.html` | Eksperto portalas (sertifikavimas) | JWT | ✓ |
| `/admin` | `admin.html` | Administravimo apžvalga | JWT + IP | ✓ |
| `/admin/projects` | `projects.html` | Projektų valdymas | JWT + IP | ✓ |
| `/admin/calls` | `calls.html` | Skambučių užklausos | JWT + IP | ✓ |
| `/admin/calendar` | `calendar.html` | Kalendorius + Schedule Engine | JWT + IP | ✓ |
| `/admin/audit` | `audit.html` | Audito žurnalas | JWT + IP | ✓ |
| `/admin/margins` | `margins.html` | Maržų taisyklės | JWT + IP | ✓ |
| `/admin/finance` | `finance.html` | Finansų knyga (ledger, dokumentai, taisyklės) | JWT + IP | ✓ |
| `/admin/ai` | `ai-monitor.html` | AI monitoring dashboard | JWT + IP | ✓ |

## Pastabos
- `backend/docs/archive/PROGRESS_LOCK.md` — istorinis darbų žurnalas (archyvas, DONE eilučių nekeisti).
- Jei reikia naujos funkcijos ar pakeitimo, pirmiausia sutikrinti su Konstitucija (`backend/VEJAPRO_KONSTITUCIJA_V2.md`).
- Visa UI sąsaja yra lietuvių kalba — keičiant tekstą naudoti teisingus diacritikus.

## Schedule Engine (2026-02-08 statusas)
- **Phase 0** (RESCHEDULE preview/confirm): DONE
- **Phase 2** (HELD rezervacijos + conversation_locks): DONE
- **Phase 3** (Daily batch approve): DONE
- **Voice webhook** (Twilio): DONE
- **Chat webhook** + web chat widget: DONE
- **Hold expiry worker**: DONE
- **Notification outbox** (SMS + Email + WhatsApp): DONE
- Technine specifikacija: `backend/SCHEDULE_ENGINE_V1_SPEC.md`
- Likę darbai: `backend/SCHEDULE_ENGINE_BACKLOG.md`

## V2.2 Unified Client Card (2026-02-09 statusas)

- **Email intake flow**: DONE — anketa, pasiūlymas, .ics, accept/reject per public link.
- **Multi-channel notification outbox**: DONE — email (SMTP + .ics), WhatsApp ping (stub), SMS (legacy).
- **client_confirmations**: DONE — pervadinta iš `sms_confirmations`, pridėtas `channel` stulpelis.
- **SYSTEM_EMAIL aktorius**: DONE — CERTIFIED→ACTIVE per email patvirtinimą.
- **Admin Calls UI**: DONE — intake anketa, pasiūlymo valdymas, evidence grid.
- **DB migracija**: `20260209_000015_unified_client_card_v22.py`.
- **Alembic HEAD**: `20260209_000015`.

## Dabartinis kursas (2026-02-09)

### CI stabilizacija — PASS
- `ruff check` PASS, `ruff format --check` PASS (96 failai), `pytest` PASS.
- Testai CI veikia in-process (be uvicorn), bet galima opt-in per `USE_LIVE_SERVER=true` + `BASE_URL=...`.
- SQLite / Postgres suderinamumas: `SELECT ... FOR UPDATE` vengimas SQLite aplinkoje (jau sutvarkytas).
- Settings cache reset: autouse fixture testuose (jau sutvarkytas).

### Liko padaryti (prioritetu tvarka)
1. **Stripe/Twilio LIVE raktu perjungimas** — siuo metu TEST rezimas.
2. **Galutinis smoke test su LIVE raktais** — pilnas srautas DRAFT->ACTIVE.
3. **Email intake smoke test** — pilnas srautas: call request → intake anketa → prepare → send offer → accept per public link.
4. **SMTP konfigūracija produkcijoje** — `.env.prod` papildyti SMTP_HOST, SMTP_USER, SMTP_PASSWORD ir tt.
5. **Alembic migracija produkcijoje** — `alembic upgrade head` (20260209_000015).
6. **Schedule Engine backlog** — zr. `SCHEDULE_ENGINE_BACKLOG.md`:
   - RESCHEDULE scope pasirinkimas (DAY/WEEK) Admin UI.
7. **Neprivalomi patobulinimai:**
   - Vision AI integracija (feature flag `ENABLE_VISION_AI`).
   - WhatsApp API integracija (vietoj stub).
   - Redis cache galerijos/projektu API.
   - CDN nuotraukoms.
