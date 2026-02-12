# Dokumentacijos ir sistemos audito ataskaita

**Data:** 2026-02-12  
**Scope:** Visa dokumentacija, .cursor rules, STATUS, Konstitucija, Techninė dokumentacija, API katalogas, infrastruktūra, saugumas

---

## 1. ĮSISAVINIMAS — SANTRAUKA

### 1.1 Core Domain (Konstitucija V2)

| Sritis | Supratimas |
|--------|------------|
| **Statusai** | DRAFT → PAID → SCHEDULED → PENDING_EXPERT → CERTIFIED → ACTIVE. Forward-only, tik per `POST /transition-status`. |
| **Mokėjimai** | Vienintelė tiesa: `payments` (provider manual/stripe). Manual = default, Stripe = optional. Idempotencija: `(provider, provider_event_id)` unikalus. |
| **DRAFT→PAID** | Reikia DEPOSIT fakto (SUCCEEDED, amount>0 arba WAIVED). SUBCONTRACTOR/ADMIN. |
| **CERTIFIED→ACTIVE** | Reikia ABU: (1) `client_confirmations` CONFIRMED (email/SMS), (2) `payments` FINAL SUCCEEDED. Email default (SYSTEM_EMAIL), SMS legacy (SYSTEM_TWILIO). |
| **Aktoriai** | SYSTEM_STRIPE, SYSTEM_TWILIO, SYSTEM_EMAIL, CLIENT, SUBCONTRACTOR, EXPERT, ADMIN. |
| **AI** | AI tik siūlo; niekada nekeičia statuso, kainos, sertifikato. |
| **Feature flags** | Isjungtas modulis → 404 (ne 403). Visi Lygio 2+ moduliai uždaromi. |
| **Audit** | Kiekvienas kritinis veiksmas → audit log su actor, IP, user_agent. PII redaguojama. |

### 1.2 Dabartinė būsena (V2.7.2)

- **374 testai**, 79 API + 18 app routes, 26 feature flags, 18 HTML puslapių
- **Production:** vejapro.lt, Cloudflare Tunnel, auto-deploy timer
- **Admin UI V3:** shared CSS/JS, sidebar, Klientų modulis, dashboard SSE, Operator Workflow
- **Email:** CloudMailin webhook, AI extract, sentiment, auto-reply
- **Saugumas:** trusted proxy, forwarded-header hardening, RBAC, PII redakcija

---

## 2. DOKUMENTACIJOS SĄLYGA

### 2.1 Pagrindiniai dokumentai (atitinka kodą)

| Dokumentas | Būsena | Pastaba |
|------------|--------|---------|
| `VEJAPRO_KONSTITUCIJA_V2.md` | ✅ Sutampa | Payments-first, V2.3 email, SYSTEM_EMAIL, 2026-02-09 |
| `VEJAPRO_TECHNINE_DOKUMENTACIJA_V2.md` | ✅ Sutampa | Schema, state machine, 2026-02-11 |
| `API_ENDPOINTS_CATALOG.md` | ✅ Sutampa | V1.52 + V2.3 + V3 + Email Webhook V2.7, 2026-02-12 |
| `README.md` | ✅ Sutampa | Architektūra, TRUSTED_PROXY_CIDRS, config.py |
| `STATUS.md` | ✅ Sutampa | V2.7.2, 374 testai, moduliai |
| `INFRASTRUCTURE.md` | ✅ Sutampa | Cloudflare, Nginx, deploy timer |
| `.env.example` | ✅ Pilnas | 26+ flags, CloudMailin, AI sentiment, admin token |

### 2.2 Dokumentacijos neatitikimai (Nedideli)

| # | Problema | Vieta | Poveikis |
|---|----------|-------|----------|
| 1 | **Techninė dok.** kalba apie `routers/` | A.1 katalogų struktūra | Faktinė struktūra yra `api/v1/*.py`, ne `routers/`. README teisingai rodo `api/v1/`. |
| 2 | **documentation.mdc** nurodo V1.3, V1.4, V1.5 | `.cursor/rules/documentation.mdc` | Kanoniniai dokumentai dabar V2. Taisyklė nereflektuoja V2. |
| 3 | **PROGRESS_LOCK.md** nuoroda | documentation.mdc | README ir docs/archive — PROGRESS_LOCK nebepaminimas kaip aktyvus. |
| 4 | **README** „Paskutinis atnaujinimas: 2026-02-11“ | backend/README.md | STATUS.md rodo V2.7.2 (02-12). Mažas skirtumas. |

### 2.3 Archyvas

- `docs/archive/` — istoriniai dokumentai (V1.*, SYSTEM_AUDIT, GO_LIVE_PLAN, DEPLOYMENT_NOTES) saugomi teisingai
- Senieji audito ataskaitos (2026-02-07, 2026-02-09) — naudingos reference, bet STATUS ir naujausi docs (V2.7) yra šaltinis

---

## 3. SAUGUMAS

### 3.1 KRITINIS — kredencialų nutekėjimas (git diff)

**Vieta:** `.claude/settings.local.json`  
**Problema:** Failas turėjo GitHub personal access token (blocked patterns masyve).

**Atlikta (2026-02-12):** Token pašalintas iš failo.

**Privaloma:** Token buvo eksponuotas — **revoke GitHub**: Settings → Developer settings → Personal access tokens → Revoke. Sukurti naują, jei reikia.

### 3.2 Kiti saugumo auditai

- **SECURITY_MIGRATION_AUDIT_2026-02-12.md** — CRITICAL/HIGH nėra. MEDIUM: CORS wildcard warning, admin token secret. LOW: FIXED.
- Trusted proxy, forwarded-header hardening (V2.7.1, V2.7.2) — dokumentuota.

---

## 4. .CURSOR RULES

| Failas | Būsena |
|--------|--------|
| `payments-first.mdc` | ✅ Atnaujinta V2.3 (email + SMS) |
| `project-overview.mdc` | ✅ Sutampa |
| `git-deploy.mdc` | ✅ Ruff, pre-push checklist |
| `documentation.mdc` | ⚠️ Nuorodos į V1.* (senos) |
| `status-transitions.mdc` | — (netikrinta) |
| `feature-flags.mdc` | — (netikrinta) |
| `testing.mdc` | — (netikrinta) |

---

## 5. MODULIŲ DOKUMENTACIJA

| Modulis | Dokumentas | Būsena |
|---------|------------|--------|
| Schedule Engine | SCHEDULE_ENGINE_V1_SPEC.md, BACKLOG | ✅ LOCKED, atitinka kodą |
| Gallery | GALLERY_DOCUMENTATION.md | — |
| Contractor/Expert | CONTRACTOR_EXPERT_PORTALS.md | — |
| Admin UI V3 | docs/ADMIN_UI_V3.md | ✅ README nuoroda |
| Client UI V3 | docs/CLIENT_UI_V3.md | ✅ API kataloge |
| Linting | LINTING.md | ✅ README nuoroda |

---

## 6. REKOMENDACIJOS

### P0 (Skubios)

1. **Kredencialai:** Patikrinti, ar `.claude/settings.local.json` nėra committinamas su token. Jei token jau remote — revoke ir rotate.

### P1 (Trumpalaikiai)

1. **documentation.mdc:** ✅ Atnaujinta — nuorodos į V2 (Konstitucija V2, Techninė V2).
2. **Techninė dok. A.1:** ✅ Pataisyta — `routers/` → `api/v1/`.

### P2 (Geriausia praktika)

1. **README:** Sinchronizuoti "Paskutinis atnaujinimas" su STATUS.md versija.
2. **PROGRESS_LOCK.md:** Patikrinti, ar egzistuoja ir ar documentation.mdc turi teisingą nuorodą.

---

## 7. IŠVADA

Dokumentacija yra **gerai struktūrizuota** ir **daugiausia atitinka dabartinį kodą (V2.7.2)**. Pagrindiniai šaltiniai (Konstitucija V2, Techninė V2, API katalogas, STATUS) yra nuoseklūs.

**Kritinis veiksmas:** užtikrinti, kad GitHub token nebūtų version control.

**Nedideli pataisymai:** documentation.mdc, katalogo struktūros pavadinimas Techninėje dok.

(c) 2026 VejaPRO. Vidinė audito ataskaita.
