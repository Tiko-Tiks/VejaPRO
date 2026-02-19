# VejaPRO Klientu Portalas — Figma Dizaino Brief'as

## 1. Projekto kontekstas

**VejaPRO** — profesionalaus vejos irengimo ir prieziuros platforma (Lietuva).
Reikia sukurti **Klientu portala** — sriti, kur klientas prisijungia ir mato savo projektu eiga, dokumentus, gali uzsakyti paslaugas ir gauti kainos ivertinima.

**Svetaine:** vejapro.lt
**Kalba:** Lietuviu (visas UI lietuviskai)
**Tiksline auditorija:** Privaciu namu savininkai (35–60 m.), technologijomis naudojasi vidutiniskai

---

## 2. Dizaino sistema (jau egzistuojanti)

### Spalvos
| Paskirtis | Spalva | HEX |
|-----------|--------|-----|
| Primary green | Profesionali zalia | `#2d7a50` |
| Primary light | Sviesnesne zalia | `#3d9464` |
| Primary dark | Tamsesne zalia | `#1e5c3a` |
| Accent gold | Silta auksine | `#b8912e` |
| Accent light | Sviesnesne auksine | `#d1a94a` |
| Ink (tekstas) | Tamsus | `#1a1a1a` |
| Secondary text | Pilkas | `#5a5a5a` |
| Muted text | Sviesiai pilkas | `#8a8a8a` |
| Background | Siltas baltas | `#faf9f6` |
| Panel/Card | Baltas | `#ffffff` |
| Border | Siltas pilkas | `#e2ddd5` |
| Success | Zalia | `#059669` |
| Error | Raudona | `#dc2626` |

### Sriftas
- **DM Sans** (Google Fonts) — body, UI elementai
- **Space Grotesk** — naudojamas dabartiniame client.html (galima suvienodinti i DM Sans)

### Kampu radiusai
- Korteles: `12px`
- Dideli paneliai: `20px`
- Badge/pill: `9999px` (full round)

### Seseliai
- Mazas: `0 2px 8px rgba(26,26,26, 0.04)`
- Vidutinis: `0 8px 24px rgba(26,26,26, 0.08)`
- Didelis: `0 20px 50px rgba(26,26,26, 0.12)`

### Logotipas
- Failas: `logo.png` (zalias fonas, baltas tekstas)
-Aukstis header'yje: 36px

---

## 3. Ekranu sarasas (6 puslapiai)

### 3.1 Prisijungimas (`/login`)
- **Jau egzistuoja** — dual-mode (admin + klientas)
- Klientas prisijungia per **magic link** (el. pastu gauna nuoroda)
- Alternatyviai: el. pastas + slaptazodis per Supabase Auth
- Po prisijungimo nukreipiama i Dashboard

### 3.2 Dashboard (`#/`)
**Pagrindinis ekranas po prisijungimo.**

Struktura nuo virsaus:
1. **Header** — logotipas + navigacija (Dashboard | Mano projektai | Ivertinti kaina | Paslaugos | Pagalba)
2. **Hero CTA zona** — 2 dideli mygtukai grid'e:
   - „Ivertinti nauja sklypa" (primary)
   - „Uzsakyti papildoma paslauga" (ghost/outline)
3. **Reikia jusu veiksmo** sekcija (jei yra):
   - Korteles su: busenos badge, pavadinimas, kito zingsnio tekstas, CTA mygtukas
   - Pvz.: `[DRAFT badge] Projektas Jonai | Apmokekite avansa | [Apmoketi depozita]`
4. **Mano projektai** — korteliu grid'as:
   - Kiekviena kortele: pavadinimas, busenos badge, trumpas aprasymas, „Atidaryti projekta" mygtukas
5. **Papildomos paslaugos** — upsell korteliu grid'as (3-6):
   - Pavadinimas, kaina, nauda, „Uzsakyti" mygtukas

**Busena kai nera projektu:** „Projektu dar nera. Pradekite nuo ivertinimo." + CTA

### 3.3 Mano projektai (`#/projects`)
- Projektu korteliu sarasas (tas pats kaip dashboard, bet tik projektai)
- Kortele: pavadinimas, busena, aprasymas, „Atidaryti"

### 3.4 Projekto detales (`#/projects/{id}`)
**Svarbiausia dalis — klientas cia mato viska apie savo projekta.**

Struktura:
1. **Busenos kortele:**
   - Busenos badge (spalvotas pill)
   - Statusas lietuviskai + paaiskinimas
   - „Kitas zingsnis:" tekstas
   - **Pagrindinis CTA mygtukas** (keiciasi pagal busena — zr. lentele zemiau)

2. **Eigos timeline** — horizontali 6 zingsniu juosta:
   ```
   [Juodrastis] -> [Avansas gautas] -> [Suplanuota] -> [Laukiama eksperto] -> [Sertifikuota] -> [Aktyvus]
   ```
   - Praeiti zingsniai: uzpildyti (zalia)
   - Dabartinis: ryskus remelis
   - Busimi: punktyrinis remelis

3. **Dokumentai** sekcija (sarasas su nuorodomis):
   - Preliminari samata
   - Avansine saskaita
   - Sutartis
   - Grafikas
   - Sertifikatas (PDF atsisiuntimas)
   - Galutine saskaita
   - Garantinis lapas
   *(rodomi tik tie, kurie aktualus pagal busena)*

4. **Mokejimu santrauka:**
   - Depozitas: APMOKETAS / LAUKIAMA
   - Galutinis: APMOKETAS / LAUKIAMA
   - Kitas zingsnis tekstas

**CTA mygtukai pagal busena:**

| Busena | Mygtukas | Tekstas |
|--------|----------|---------|
| DRAFT (laukia kainos) | Secondary | Perziureti ivertinima |
| DRAFT (reikia apmoketi) | Primary | Apmoketi depozita |
| PAID (sutartis nepasirasyta) | Primary | Pasirastyti sutarti |
| PAID (sutartis pasirasyta) | Secondary | Perziureti grafika |
| SCHEDULED | Secondary | Perziureti projekta |
| PENDING_EXPERT | Secondary | Perziureti projekta |
| CERTIFIED (likutis) | Primary | Apmoketi likuti |
| CERTIFIED (patvirtinti) | Primary | Patvirtinti |
| ACTIVE | Primary | Uzsisakyti prieziura |

### 3.5 Kainos ivertinimas (`#/estimate`)
**Vedlys (wizard) — 4 zingsniai:**

**1 zingsnis: Plotas**
- Laukas: „Sklypo plotas (m2)" (number input)
- Nuotrauku ikelimas (neprivaloma): drag & drop arba file picker
- Mygtukas: „Toliau"

**2 zingsnis: AI analize (rezultatas)**
- Sudetingumo lygis: LOW / MED / HIGH (vizualiai)
- Kainos diapazonas: pvz. „960 EUR – 1 440 EUR"
- Pasitikejimo indikatorius: zalia/geltona/raudona juosta
- Mygtukas: „Pasirinkti priedus"

**3 zingsnis: Priedai**
- Checkbox sarasas su kainomis:
  - Laistymo sistema (nuo 299 EUR)
  - Premium sekla (nuo 89 EUR)
  - Startinis tresimas (nuo 49 EUR)
  - Vejos robotas (kaina po ivertinimo)
- Galutine suma su breakdown
- Mygtukas: „Pateikti uzklausa"

**4 zingsnis: Patvirtinimas**
- „Pateikta ekspertui. Netrukus susisieksime."
- Mygtukas: „Grizti i Dashboard"

**Svarbu:** Kainu vedlys rodo **DISCLAIMER** — „Kainos yra preliminarios ir gali keistis po eksperto apziuros."

### 3.6 Papildomos paslaugos (`#/services`)
- Korteliu grid'as (3-6 korteles)
- Kiekviena kortele:
  - Pavadinimas
  - Kaina (pvz. „nuo 299 EUR" arba „Kaina po ivertinimo")
  - Nauda (1 sakinys)
  - „Uzsakyti" mygtukas
- Paspaudus „Uzsakyti" — modal arba mini forma su klausimais (jei yra)

**Paslaugu sarasas:**

*Naujiems projektams:*
| Paslauga | Kaina |
|----------|-------|
| Laistymo sistema | nuo 299 EUR |
| Premium sekla | nuo 89 EUR |
| Startinis tresimas | nuo 49 EUR |
| Vejos robotas | Kaina po ivertinimo |

*Aktyviems projektams:*
| Paslauga | Kaina |
|----------|-------|
| Prieziuros planas | nuo 29 EUR/men |
| Tresimo planas | Kaina po ivertinimo |
| Diagnostika (nedygsta/liga) | Kaina po ivertinimo |
| Roboto servisas | nuo 59 EUR |

### 3.7 Pagalba (`#/help`)
- Statinis puslapis
- Kontaktai: el. pastas, telefonas
- DUK sekcija (galima prideti veliau)

---

## 4. Komponentu biblioteka (reikia sukurti)

### Navigacija
- **Header:** logotipas kaireje + horizontalus meniu + profilio ikona/atsijungimas
- **Aktyvus tab:** zalia fono spalva, tamsi zalia teksto spalva
- **Mobile:** hamburger meniu

### Korteles
- **Project card:** border, radius 12px, padding 16px, shadow-sm
- **Action card:** su badge + CTA
- **Upsell card:** kompaktiska, su kaina ir mygtuku
- **Service card:** su kaina, nauda, uzsakymo mygtuku

### Mygtukai
- **Primary:** zalias fonas, baltas tekstas, radius 12px
- **Ghost/Outline:** baltas fonas, pilkas border, tamsus tekstas
- **Large CTA:** didesnis padding (16px 24px), 16px sriftas

### Badge/Pill
- Rounded pill (border-radius: 9999px)
- Zalia fono spalva (rgba), tamsiai zalias tekstas
- Busenu spalvos:
  - DRAFT: pilka
  - PAID: melyna
  - SCHEDULED: geltona
  - PENDING_EXPERT: oranzine
  - CERTIFIED: zalia
  - ACTIVE: ryskiai zalia

### Timeline
- Horizontali juosta su 6 zingsniais
- Praeiti: uzpildytas fonas (zalia)
- Dabartinis: ryskus remelis
- Busimi: punktyrinis remelis
- Mobile: vertikali

### Form elementai
- Input: radius 12px, border pilkas, padding 12px
- Checkbox: custom stilius
- File upload: drag & drop zona

---

## 5. Responsive breakpoints

| Plotis | Aprasymas |
|--------|-----------|
| > 860px | Desktop — 2 stulpeliu grid |
| 768-860px | Tablet — 1 stulpelis, mazesni padding'ai |
| < 768px | Mobile — 1 stulpelis, hamburger meniu, didesni touch target'ai (min 44px) |

**Mobile prioritetai:**
- Mygtukai min 44px aukscio
- Input min 44px aukscio, 16px sriftas (apsauga nuo zoom iOS)
- Korteles pilno plocio
- Timeline vertikali
- Navigacija hamburger + slide-out

---

## 6. User flow (pagrindiniai scenarijai)

### Naujas klientas:
```
Magic link el. pastu -> Dashboard (tuscias) -> „Ivertinti nauja sklypa" ->
Vedlys (plotas -> AI analize -> priedai -> pateikti) -> Dashboard su DRAFT projektu
```

### Egzistuojantis klientas:
```
Prisijungimas -> Dashboard -> „Reikia jusu veiksmo" kortele ->
Projekto detales -> CTA veiksmas (moketi/pasirastyti/patvirtinti)
```

### Aktyvus klientas:
```
Dashboard -> Projekto detales (ACTIVE) -> Dokumentai (sertifikatas, garantija) ->
Papildomos paslaugos -> Uzsakyti prieziura
```

---

## 7. Deliverables (ko tikimasi is dizainerio)

1. **Komponentu biblioteka** Figma'oje (buttons, cards, badges, inputs, navigation)
2. **6 desktop ekranai** (Dashboard, Projects, Project Detail, Estimate wizard, Services, Help)
3. **6 mobile ekranai** (tie patys, adaptuoti)
4. **2 empty states** (Dashboard be projektu, Projektu sarasas tuscias)
5. **CTA variantai** — kiekviena projekto busena (6 variantai projekto detaliu puslapyje)
6. **Estimate wizard** — 4 zingsniu flow
7. **Prototype** — pagrindinis flow (Dashboard -> Project -> CTA)
