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
- `STATUS.md` — **gyvas projekto statusas** (moduliai, testai, kas liko)
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

## Dabartinis statusas

Detali informacija: `STATUS.md` (moduliai, testai, kas liko, production checklist).
