# VejaPRO Admin Panel — Figma Dizaino Brief'as

## 1. Projekto kontekstas

**VejaPRO** — profesionalaus vejos irengimo ir prieziuros platforma.
Admin panelis skirtas **vienam operatoriui** (verslo savininkas), kuris valdo visa darbo procesa: nuo uzklausos gavimo iki projekto uzbaigimo. Tai yra **SaaS stiliaus** darbo irankis (panasus i Stripe Dashboard / Linear / Notion).

**Svetaine:** vejapro.lt/admin
**Kalba:** Lietuviu (visas UI lietuviskai)
**Vartotojas:** 1 administratorius (vejos irengimo verslo savininkas)

---

## 2. Dizaino sistema (V6.0)

### Temos: Light + Dark
- Default: **Light** tema
- Perjungimas per toggle mygtuka sidebar/topbar (ikona)
- Tema saugoma `localStorage` — turi islikti po perkrovimo
- **Jokiu dekoraciniu efektu** — joks noise, glow, glass. Svarus profesionalus SaaS stilius

### Spalvos — Light tema
| Paskirtis | HEX |
|-----------|-----|
| Background | `#f8f7f4` |
| Surface/Card | `#ffffff` |
| Text primary | `#1a1a1a` |
| Text secondary | `#6b6b6b` |
| Text muted | `#9a9a9a` |
| Border | `#e5e2dc` |
| Accent (primary) | `#2d7a50` |
| Accent hover | `#1e5c3a` |
| Error | `#dc2626` |
| Warning | `#f59e0b` |
| Success | `#059669` |

### Spalvos — Dark tema
| Paskirtis | HEX |
|-----------|-----|
| Background | `#111118` |
| Surface/Card | `#1c1c25` |
| Text primary | `#e8e6e1` |
| Text secondary | `#9a9a9a` |
| Border | `#2a2a35` |
| Accent | `#4ade80` |

### Sidebar (visada tamsus abiejose temose)
| Paskirtis | HEX |
|-----------|-----|
| Sidebar background | `#1a1a2e` |
| Sidebar text | `#c8c8d0` |
| Sidebar hover | `rgba(255,255,255,0.08)` |
| Sidebar active | `rgba(255,255,255,0.12)` |

### Sriftas
- **DM Sans** (Google Fonts) — visur
- Svoriai: 400 (body), 500 (labels), 600 (headings), 700 (emphasis)

### Kampu radiusai
- Korteles: `12px`
- Mygtukai: `8px`
- Input: `8px`
- Badge/pill: `9999px`

---

## 3. Layout struktura

### Ops V1 puslapiai (Planner, Project Day, Client Card, Archive)
- **Topbar layout** (`data-layout="topbar"`)
- Pilno plocio turinys, be sidebar
- Virsuje: puslapio pavadinimas + veiksmo mygtukai

### Legacy puslapiai (Projects, Customers, Finance, Calls, Calendar, Audit, AI, Margins)
- **Sidebar layout** (240px kaireje)
- Sidebar: tamsus fonas, navigacijos nuorodos, tema toggle, atsijungimo mygtukas
- Turinys desineje su `padding-left: 240px`

### Mobile (< 768px)
- Sidebar virsta overlay (hamburger meniu)
- Touch target'ai: min 48px
- Lenteles -> korteliu layout

---

## 4. Ekranu sarasas (15 admin puslapiu)

### 4.1 Prisijungimas (`/admin/login`)
- El. pastas + slaptazodis (Supabase Auth)
- „Prisijungti" mygtukas
- Klaidos pranesimas jei neteisingi duomenys
- Logotipas virsuje

---

### 4.2 Planner — Pagrindinis dashboard (`/admin`)
**Pagrindiné operatoriaus darbo vieta — kalendorius + inbox.**

Layout: 2 stulpeliai (50/50)

**Kaire puse — Kalendorius:**
- Menesio kalendorius su navigacija (<- Siandien ->)
- Menesio pavadinimas (pvz. „2026 m. vasaris")
- Dienos langeliai su skaiciumi darbu (badge)
- Po kalendoriumi: **Dienos santrauka**
  - KPI: „Dienos darbai: 3" | „Planuotos valandos: 6.5 val."
  - Dienos darbu sarasas (list items):
    - Kiekvienas: laikas, kliento vardas, projekto statusas, veiksmo mygtukas „Atidaryti"
    - Spalvotas prioriteto taskas (raudonas/geltonas/pilkas)

**Desine puse — Inbox (Needs Human):**
- Pavadinimas + „Atnaujinti" mygtukas
- Uzklausu kiekis: badge su skaiciumi
- Sarasas kortelemis:
  - Kiekviena: tipas (badge), kliento vardas, problema, laikas, CTA mygtukas
  - Tipai: NEW_CALL, ATTENTION_PROJECT, HELD_APPOINTMENT, SERVICE_REQUEST
  - Rusiuota pagal prioriteta

---

### 4.3 Project Day — Dienos darbo vaizdas (`/admin/project-day`)
**Kai operatorius atvyksta i objekta.**

Struktura nuo virsaus:
1. **Header:** Projekto pavadinimas + mygtukai: „<- Atgal" | „Atvykau" | „Ikelti foto" | „Uzbaigti"
2. **Sios dienos uzduotis** panele:
   - Grid: Projektas (ID) | Diena | Planuota trukme | Biudzetas
   - **Checklist** — uzduociu sarasas su checkbox'ais:
     - Patikrinti teritorija
     - Paruosti dirva
     - Kloti veja
     - Fotografuoti rezultata
3. **Irodymai (nuotraukos)** sekcija:
   - Kategorijos dropdown: SITE_BEFORE / WORK_IN_PROGRESS / EXPERT_CERTIFICATION
   - File upload mygtukas
   - Nuotrauku grid'as (thumbnail'ai su data)
4. **Auditas** — timeline su veiksmu istorija

---

### 4.4 Client Card — Kliento kortele (`/admin/client-card`)
**Viskas apie viena klienta vienoje vietoje.**

Struktura:
1. **Header:** Kliento vardas + mygtukai: „<- Planner" | „Generuoti" | „Patvirtinti" | „Koreguoti" | „Ignoruoti"
2. **Summary** panele (4 stulpeliai grid):
   - Stadija | Depozitas | Kitas vizitas | Uzdirba
   - Attention flags (spalvoti badge'ai)
3. **AI Kainu pasiulymas** panele:
   - Status line
   - Decision badge (approved/edited/ignored)
   - Grid: Bazine kaina | AI korekcija | Final pasiulymas | Kainos rezis | Confidence | Susije projektai
   - Reasoning (italics tekstas korteleje)
   - Faktoriai sarasas
4. **Collapsible sekcijos** (`<details>`):
   - Vietos anketa (dirvozemis, nuolydis, augalija, priejimas, atstumas, kliutys)
   - Projektai
   - Skambuciai/laiskai
   - Mokejimai
   - Nuotraukos
   - Timeline

**Modal: Koreguoti kaina**
- Input: Nauja kaina (EUR)
- Textarea: Priezastis (min 8 simboliai)
- Mygtukai: Atsaukti | Issaugoti

---

### 4.5 Archyvas (`/admin/archive`)
**Klientu ir projektu paieska/filtravimas.**

1. **Paieskos panele:**
   - Teksto input (placeholder: „Ieskoti pagal kliento varda, kontakta, projekto ID ar statusa...")
   - Mygtukai: Ieskoti | Isvalyti | Atnaujinti
2. **Filtrai (inline):**
   - Rezimas: Be demesio | Needs human | Visi
   - Statusas: Visi / DRAFT / PAID / SCHEDULED / PENDING_EXPERT / CERTIFIED / ACTIVE
   - Rusiuoti: Naujausi | Pagal varda | Pagal projektu kieki
3. **Rezultatu sarasas** — klientu korteles su projektu info

---

### 4.6 Legacy Dashboard (`/admin` kai Ops V1 isjungtas)
**Alternatyvus dashboard su sidebar.**

1. **4 stat korteles** (horizontalus grid):
   - Reikia veiksmo (skaicius)
   - Laukia patvirtinimo (skaicius)
   - Nepavyke pranesimai (skaicius)
   - Nauji skambuciai (skaicius)
2. **Darbo eiles lentele:**
   - Stulpeliai: Prioritetas (raudonas/geltonas/pilkas) | Klientas | Problema | Statusas | Paskutinis veiksmas | Veiksmas
   - Tabs: Aktyvus / Archyvas
3. **SSE real-time** — automatiniai atnaujinimai kas 5 sek

---

### 4.7 Projektai (`/admin/projects`)
**Visu projektu lentele su filtrais.**

1. **Filter chips** (horizontalus toggle mygtukai):
   - Juodrastis | Apmoketas | Suplanuotas | Laukia eksperto | Sertifikuotas | Aktyvus | Laukiantys veiksmo (default)
2. **Mini triage** — mazas langelis su svarbiausia info
3. **Lentele:**
   - Stulpeliai: ID (trumpas) | Klientas | Statusas (badge) | Suma | Data | Veiksmas
   - Eilutes su urgency spalvomis (high=raudona, medium=geltona, low=pilka)
   - Kiekviena eilute: PRIMARY mygtukas (next_best_action)
4. **Modalai:**
   - Projekto detales
   - Rankinis mokejimas (depozitas/galutinis)
   - Kliento tokeno generavimas
   - Priskyrti eksperta

---

### 4.8 Klientai (`/admin/customers`)
**Klientu sarasas.**

1. **Filter chips:** Laukia patvirtinimo | Nepavyke pranesimai
2. **Lentele:**
   - Klientas (maskuotas) | Projektu kiekis | Statusas | Urgency | Veiksmas
   - Urgency eilutes (high/medium/low)
3. Paspaudus -> atidaro kliento profili

---

### 4.9 Kliento profilis (`/admin/customer-profile`)
**Tabs su visa info apie klienta.**

Tabs:
- **Summary** (pirmas, default) — AI next action pill + PRIMARY mygtukas
- Projektai — sarasas
- Skambuciai — sarasas
- Mokejimai — lentele
- Pranesimai — outbox

---

### 4.10 Finansai (`/admin/finance`)
1. **Metrics korteles** (SSE real-time): Pajamos | Laukiami | Sio men. | Mokejimu sk.
2. **Mini triage:** Laukiantys mokejimai
3. **Lentele:** mokejimu sarasas
4. **Quick actions:** record_deposit, record_final

---

### 4.11 Skambuciai (`/admin/calls`)
- Skambuciu sarasas/lentele
- Filtrai pagal data, statusa
- Detaliu modal

---

### 4.12 Kalendorius (`/admin/calendar`)
- Vizitas planavimo sasaja
- Collapsible advanced sekcijos: Planavimo irankiai, Hold irankiai, Perplanavimas
- Flatpickr data picker

---

### 4.13 Auditas (`/admin/audit`)
- Audito log sarasas
- Filtrai: entity_type, actor_type, data
- Lentele: laikas | veiksmas | entity | actor

---

### 4.14 AI monitorius (`/admin/ai`)
- AI sprendimu stebesena
- Global Attention: zemi confidence
- AI summary: „Patikrinti N klaidu"

---

### 4.15 Marzos (`/admin/margins`)
- Marzu skaiciuokle
- Preview kalkuliatorius (auksinis bar'as)
- CRUD lentele

---

## 5. Komponentu biblioteka

### Navigacija
- **Sidebar (legacy):** 240px, tamsus (#1a1a2e), meniu items, tema toggle, atsijungimas
- **Topbar (Ops V1):** puslapio pavadinimas + veiksmo mygtukai desineje
- **Breadcrumb:** „<- Atgal i planner" stiliaus nuorodos

### Stat korteles
- Kompaktiskos (4 per eilute)
- Skaicius (didelis), label (mazas), subtext (muted)
- Spalvotas akcentas pagal tipa

### Lenteles
- Zebra striping (kas antra eilute tamsesne)
- Urgency eilutes: `row-urgency-high` (rausva), `medium` (geltona), `low` (pilka)
- Hover efektas
- Action mygtukas kiekvienoje eiluteje

### Priority dots
- High: `#dc2626` (raudonas)
- Medium: `#f59e0b` (geltonas)
- Low: `#d1d5db` (pilkas)

### Filter chips
- Horizontalus toggle mygtukai
- Aktyvus: zalias fonas + tamsus tekstas
- Neaktyvus: pilkas border

### Badge/Pill
| Busena | Spalva |
|--------|--------|
| DRAFT | Pilka |
| PAID | Melyna |
| SCHEDULED | Geltona |
| PENDING_EXPERT | Oranzine |
| CERTIFIED | Zalia |
| ACTIVE | Ryskiai zalia |

### Mygtukai
- **Primary:** zalias fonas, baltas tekstas
- **Secondary:** pilkas fonas
- **Ghost:** transparent + border
- **XS:** mazas (kalendoriaus navigacija)
- **Danger:** raudonas (pavojingi veiksmai)

### Modal
- Tamsus backdrop
- Balta kortele su header + body + footer
- Close (x) mygtukas
- Responsive (95% plocio mobile)

### Toast pranesimai
- Apacioje desineje
- Success (zalia), Error (raudona), Info (melyna)
- Auto-dismiss po 5 sek

### Collapsible sekcijos (`<details>`)
- Summary eilute su rodykle
- Turinys paslepiamas/rodomas
- Naudojama Client Card, Calendar

### PII maskavimas
- El. pastas: `j***@v***.lt`
- Telefonas: `+3706*****12`
- Niekada nerodyti pilno el. pasto/telefono

---

## 6. User flows

### Dienos darbo flow:
```
Planner (kalendorius) -> Pasirinkti diena -> Dienos darbu sarasas ->
Atidaryti projekta -> Project Day -> Atvykau -> Checklist ->
Ikelti foto -> Uzbaigti diena -> Grizti i Planner
```

### Naujo kliento flow:
```
Inbox (Needs Human) -> Naujas skambutis/laiskas ->
Client Card -> Generuoti AI kaina -> Patvirtinti/Koreguoti ->
Sukurti projekta -> Siusti pasiulyma klientui
```

### Mokejimo flow:
```
Planner/Inbox -> Klientas apmokejo -> Projects ->
Rankinis mokejimas (modal) -> Statusas pasikeicia automatiskai
```

---

## 7. Deliverables

1. **Komponentu biblioteka** — sidebar, topbar, stat cards, tables, filter chips, badges, buttons, modals, toasts, priority dots, forms, collapsible sections
2. **Light + Dark tema** — visi komponentai abiejose temose
3. **15 desktop ekranu:**
   - Login
   - Planner (kalendorius + inbox)
   - Project Day (checklist + foto upload)
   - Client Card (summary + AI pricing + sekcijos)
   - Archive (paieska + filtrai)
   - Legacy Dashboard (stat cards + darbo eile)
   - Projects (filtrai + lentele + modalai)
   - Customers (sarasas)
   - Customer Profile (tabs)
   - Finance (metrics + lentele)
   - Calls (sarasas)
   - Calendar (planavimas)
   - Audit (log sarasas)
   - AI Monitor
   - Margins (skaiciuokle)
4. **5 mobile ekranai** (svarbiausi): Login, Planner, Project Day, Client Card, Projects
5. **3 modalai:** Projekto detales, Rankinis mokejimas, Kainos koregavimas
6. **Empty states:** Dashboard be darbu, Inbox tuscias, Projektai be rezultatu
7. **Prototype:** Planner -> Project Day -> Client Card flow

---

## 8. Prioritetu eile dizaineriui

| Prioritetas | Ekranas | Kodel |
|-------------|---------|-------|
| P1 | Planner + Inbox | Pagrindinis darbo vaizdas, naudojamas kasdien |
| P1 | Client Card | Visi klientu veiksmai vienoje vietoje |
| P1 | Project Day | Lauko darbu vaizdas |
| P2 | Projects lentele | Daznai naudojama |
| P2 | Archive | Paieska |
| P2 | Login | Pirmasis kontaktas |
| P3 | Finance, Customers, Calendar | Retesni puslapiai |
| P3 | Audit, AI, Margins, Calls | Pagalbiniai |
