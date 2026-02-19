# VejaPRO Viesieji Puslapiai — Figma Dizaino Brief'as

## 1. Projekto kontekstas

**VejaPRO** — profesionalaus vejos irengimo ir prieziuros platforma (Lietuva).
Viesieji puslapiai — tai pirmasis kontaktas su potencialiu klientu. Svetaine turi atrodyti **profesionaliai, patikimai ir moderniai** (SaaS stiliaus landing page). Tikslas — konvertuoti lankytojus i registracijas arba uzklausas.

**Svetaine:** vejapro.lt
**Kalba:** Lietuviu (visas UI lietuviskai, `lang="lt"`)
**Tiksline auditorija:** Privaciu namu savininkai (30–60 m.), ieskantys profesionalaus vejos irengimo paslaugu

---

## 2. Dizaino sistema (Public Design System V1.0)

### Spalvu palete (Green/Gold)
| Paskirtis | CSS kintamasis | HEX |
|-----------|----------------|-----|
| Primary green | `--vp-primary` | `#2d7a50` |
| Primary light | `--vp-primary-light` | `#3d9464` |
| Primary dark | `--vp-primary-dark` | `#1e5c3a` |
| Primary deep | `--vp-primary-deep` | `#122e1e` |
| Primary mist | `--vp-primary-mist` | `rgba(45, 122, 80, 0.05)` |
| Accent gold | `--vp-accent` | `#b8912e` |
| Accent light | `--vp-accent-light` | `#d1a94a` |
| Accent subtle | `--vp-accent-subtle` | `rgba(184, 145, 46, 0.07)` |
| Ink (tekstas) | `--vp-ink` | `#1a1a1a` |
| Secondary text | `--vp-ink-secondary` | `#5a5a5a` |
| Muted text | `--vp-ink-muted` | `#8a8a8a` |
| Background | `--vp-bg` | `#faf9f6` |
| White surface | `--vp-bg-white` | `#ffffff` |
| Warm background | `--vp-bg-warm` | `#f5f3ee` |
| Mist background | `--vp-bg-mist` | `#f0f5f2` |
| Border | `--vp-border` | `#e2ddd5` |
| Border light | `--vp-border-light` | `#edeae4` |
| Success | `--vp-success` | `#059669` |
| Error | `--vp-error` | `#dc2626` |

### Sriftas
- **DM Sans** (Google Fonts) — visur (body, headings, UI)
- Svoriai: 400 (body), 500 (labels, nav), 700 (headings, emphasis)
- CSS: `--vp-font-body: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`

### Kampu radiusai
| Elementas | Reiksme | CSS kintamasis |
|-----------|---------|----------------|
| Korteles, mygtukai | `12px` | `--vp-radius` |
| Dideli paneliai, sekcijos | `20px` | `--vp-radius-lg` |
| Badge, pill, filtrai | `9999px` | `--vp-radius-full` |

### Seseliai
| Lygis | Reiksme | CSS kintamasis |
|-------|---------|----------------|
| Small | `0 2px 8px rgba(26, 26, 26, 0.04)` | `--vp-shadow-sm` |
| Medium | `0 8px 24px rgba(26, 26, 26, 0.08)` | `--vp-shadow-md` |
| Large | `0 20px 50px rgba(26, 26, 26, 0.12)` | `--vp-shadow-lg` |
| Accent glow | `0 0 40px rgba(184, 145, 46, 0.12)` | `--vp-accent-glow` |

### Tarpai
- Sekciju tarpas: `100px` (desktop), `72px` (tablet), `56px` (mobile)
- Konteineris: `max-width: 1180px`, `padding: 0 24px`
- Platus konteineris (galerija): `max-width: 1400px`

### Logotipas
- Failas: `logo.png?v=2`
- Aukstis header'yje: `36px`

---

## 3. Ekranu sarasas (4 puslapiai)

### 3.1 Landing — Pagrindinis puslapis (`/`)
**Ilgas, vieno puslapio layout su 7 sekcijomis + header + footer.**

#### Header (sticky, fixed)
- **Transparent** virsuje (hero fone) — baltas tekstas
- **Scrolled** (po 60px scroll) — baltas fonas, blur backdrop, seselis
- Struktura: Logo (kaire) | Nav nuorodos (centras) | Auth mygtukai (desine) | Hamburger (mobile)
- Nav nuorodos: Paslaugos | Darbu pavyzdziai | Kaip vyksta | Kainos | Kontaktai
- Auth: „Prisijungti" (link) | „Registruotis" (link) | „Gauti pasiulyma" (primary btn)

#### Sekcija 1: Hero
- **Pilno ekrano** sekcija su foniniu vaizdu (`hero-landing.png`)
- Zalias overlay gradientas (160deg, 82% -> 55% opacity)
- Triuksminis teksturos sluoksnis (subtilus noise SVG)
- Auksinis radialinis akcentas desiniame virsutiniame kampe
- **Turinys (centras):**
  - H1: „*Profesionalus vejos irengimas* su premium kokybes eiga nuo pirmo zingsnio" (italic emfaze „Profesionalus vejos irengimas")
  - P: „Jauna, bet patyrusi komanda su 5+ metu praktika..."
  - 2 mygtukai: „Gauti pasiulyma" (primary) + „Ziureti darbu pokycius" (secondary/glass)
- **Trust bar** po mygtukais (3 elementai):
  - Pries / Po fotofiksacija (su SVG ikona)
  - Premium kokybes irengimas
  - Viskas vienoje paskyroje
- **Animacijos:** `vpFadeUp` — H1 (0.1s delay), P (0.25s), mygtukai (0.4s)

#### Sekcija 2: Darbu pavyzdziai (Featured Works)
- Baltas fonas (`--vp-bg-white`)
- Section header: label „Rezultatai" + H2 „Musu darbu pavyzdziai" + paaiskinimasas
- **3 stulpeliu grid** (desktop) su nuotrauku kortelemis:
  - Kraunama is API: `GET /api/v1/gallery?featured_only=true&limit=6`
  - Kiekviena kortele: thumbnail + hover overlay „Perziureti pries / po"
  - Featured badge (auksinis), Location badge (baltas, apacioje kaireje)
  - Paspaudus atidaromas lightbox
- CTA: „Perziureti visa galerija" (outline mygtukas)

#### Sekcija 3: Paslaugos (Services)
- Numatytas fonas (`--vp-bg`)
- Section header: label „Paslaugos" + H2 + paaiskinimasas
- **3 korteliu grid** (desktop, 1 stulpelis mobile):
  - Kiekviena kortele (`vp-card`):
    - SVG ikona (56x56, zalio gradiento fonas)
    - H3 pavadinimas
    - Bullet sarasas (2 punktai su zaliomis bullet skrituliukais)
    - Ghost CTA mygtukas: „Prisijungti ir ivertinti projekta"
  - Paslaugos: Vejos irengimas | Vejos prieziuros planas | Aplinkos formavimas ir projektavimas
- Hover: kortele pakyla (-4px), atsiranda seselis + virsutinis gradient bar (green->gold)

#### Sekcija 4: Procesas (Process)
- Siltas fonas (`--vp-bg-warm`)
- Section header: label „Procesas" + H2 + „5 aiskus zingsniai..."
- **5 zingsniu timeline** (horizontali desktop, vertikali mobile):
  - Kiekvienas zingsnis:
    - Apvalus skaicius (52x52, zalias fonas, baltas tekstas)
    - H3 pavadinimas
    - P paaiskinimasas
  - Linija tarp zingsniu (gradient, 30% opacity)
  - Hover: skaicius pasikeicia i auksini fona + dideja (scale 1.08)
  - Zingsniai: 1) Prisijungimas + klausimynas → 2) Ivertinimas → 3) Suderinimas → 4) Darbai + fotofiksacija → 5) Perdavimas
- CTA: „Gauti pasiulyma" (green mygtukas)

#### Sekcija 5: Kainos (Pricing)
- Numatytas fonas (`--vp-bg`)
- Section header: label „Kainos" + H2 „Preliminari kaina po klausimyno" + paaiskinimas
- **3 korteliu grid** (3 zingsniai, ne kainos!):
  1. „Prisijunkite" — kliento paskyra (outline btn)
  2. „Uzpildykite klausimyna" — ~2-4 min (primary btn, `highlight` kortele su auksiniu border)
  3. „Gaunate preliminaria kaina" — automatiskai (outline btn)
- **Kainos faktoriai** (po kortelemis):
  - H3: „Kas itraukiama i preliminaria kaina?"
  - 2x2 grid: Plotas ir forma | Grunto paruosimas | Reljefo ypatumai | Privazavimas ir medziagos
  - Kiekvienas faktorius: ikona (32x32) + tekstas
- CTA: „Pradeti profesionalu vejos irengima" (primary mygtukas)

#### Sekcija 6: Garantijos (Trust)
- Misty fonas (`--vp-bg-mist`)
- Section header: label „Garantijos" + H2 „Kodel galite mumis pasitiketi" + „Procesiniai irodymai..."
- **4 korteliu grid** (desktop, 2 tablet, 1 mobile):
  - Kiekviena kortele:
    - Ikona (56x56, primary-mist fonas, zalias SVG)
    - H3 pavadinimas
    - P paaiskinimasas
  - Korteles: Fotofiksacija | Aiskus pasiulymas | Aiski eiga | Terminai ir atsakomybe
- CTA: „Perziureti darbus" (outline mygtukas)

#### Sekcija 7: Kontaktai / Lead Capture forma
- Gradientinis fonas (`--vp-bg` -> `--vp-bg-warm`)
- Section header: label „Kontaktai" + H2 + paaiskinimas
- **2 stulpeliu layout** (info kaire, forma desine):
  - **Kaire — Kontaktine informacija:**
    - H3: „Kaip galime padeti?"
    - P: paaiskinimasas
    - 3 kontaktu eilutes su ikonomis:
      - Telefonas: +37065849514
      - El. pastas: info@vejapro.lt
      - Darbo laikas: I–V: 8:00 – 18:00
  - **Desine — Uzklausos forma (kortele su seseliu):**
    - Virsutinis gradient bar (green->gold, 3px)
    - H3: „Uzklausos forma"
    - Subtitle: „Laukai pazymeti * yra privalomi"
    - Laukai (2 stulpeliu grid):
      - Vardas * (text input)
      - Telefonas * (tel input, pattern validation)
      - Miestas/rajonas (select: Vilnius, Kaunas, Klaipeda, Siauliai, Panevezys, Kitas)
      - Paslauga (select: Vejos irengimas, Vejos prieziura, Apzeldinimas, Konsultacija, Kita)
    - Submit: „Siusti uzklausa" (green, full-width)
    - Privacy: „Jusu duomenys naudojami tik susisiekimui..."
    - Submit siuncia i: `POST /api/v1/call-requests`

#### Footer
- Tamsus fonas (`--vp-primary-deep`, #122e1e)
- **4 stulpeliu grid:**
  - Brand: VejaPRO + aprasymas + kontaktai
  - Paslaugos: 3 nuorodos
  - Navigacija: Galerija, Kaip vyksta, Kainos, Kontaktai
  - Paskyra: Prisijungti, Registruotis
- Apatine juosta: copyright + el. pasto nuoroda

#### Mobile Sticky Bar
- Rodomas tik < 768px
- Fiksuotas apacioje
- 2 mygtukai: „Skambinti" (outline) + „Gauti pasiulyma" (primary)

---

### 3.2 Galerija (`/gallery`)
**Atskiras puslapis su pries/po nuotrauku galerija.**

#### Gallery Hero
- Gradientinis fonas (primary-deep -> primary -> primary-dark)
- Triuksminis SVG sluoksnis + auksinis radialinis akcentas
- H1: „Musu projektu galerija"
- P: paaiskinimas
- **3 stat korteles** (horizontalus grid):
  - Projektu (skaicius, API-driven)
  - Iskirtiniai (skaicius)
  - Regionai (skaicius)
  - Stilius: puspraskistes stiklo efektas (blur 8px, baltas 8% fonas)

#### Filtru juosta (sticky, z-index 90)
- Prilitpusi po header (top: 65px)
- Blur backdrop
- Horizontalus filter mygtukai (pill formos):
  - „Visi projektai" (default aktyvus)
  - „Iskirtiniai"
  - Lokacijos filtrai (dinamiskai is API)
  - Aktyvus: zalias fonas, baltas tekstas

#### Galerijos grid
- `auto-fill, minmax(300px, 1fr)` grid
- **Nuotrauku korteles** (`vp-photo-card`):
  - 4:3 aspect ratio
  - Thumbnail su lazy loading
  - Placeholder animacija (pulse) kol kraunasi
  - Featured badge (auksinis, virsuje desineje)
  - Location badge (baltas, apacioje kaireje)
  - Hover: overlay su „Perziureti pries / po" tekstu + pakyla (-4px)
  - Paspaudus: atidaromas lightbox
- **Infinite scroll:** IntersectionObserver su sentinel elementu
- **Empty state:** augalo ikona + „Projektu nerasta" + „Isvalyti filtrus" mygtukas
- **Loader:** spinner animacija + „Kraunama..." tekstas

#### Lightbox (Before/After Slider)
- Pilno ekrano modal (tamsus 95% fonas)
- Balta kortele (border-radius 12px) su:
  - **Slider:** pries/po nuotraukos su vilkimo rankena
  - Rankena: baltas apvalus mygtukas (48x48) su zalios rodykles
  - Etiketés: „Pries" (kaireje, pilkas) + „Po" (desineje, zalias)
  - Close (x) mygtukas (virsuje desineje)
  - Lokacijos info po slider'iu
- **Touch support:** mouse + touch drag
- **Keyboard:** Escape uzdaro

---

### 3.3 Prisijungimas (`/login`)
**Centruota auth forma ant silto fono.**

- **Auth shell:** `min-height: 100vh`, centruotas, `--vp-bg-warm` fonas
- **Auth card** (max-width 420px):
  - Virsutinis gradient bar (green->primary-light, 3px)
  - Seselis: `--vp-shadow-lg`
  - **Brand zona:** logotipas (centras) + H1 „Prisijungimas" + subtitle
  - **Forma:**
    - El. pastas (email input, autocomplete)
    - Slaptazodis (password input, autocomplete)
    - „Prisijungti" mygtukas (green, full-width)
  - **Klaidos pranesimas:** raudona zona su tekstu
  - **Nuorodos:**
    - „Neturite paskyros? Registruotis" (link)
    - „Grizti i pradzia" (muted link)
- **Dual-mode:** `/login` (klientas) vs `/admin/login` (admin) — skirtingos sesiju rakstes ir redirect'ai
- **Supabase Auth:** naudoja `@supabase/supabase-js` CDN

---

### 3.4 Registracija (`/register`)
**Ta pati auth-shell struktura kaip ir login.**

- **Auth card:**
  - Brand: logotipas + H1 „Sukurkite paskyra" + „Registruokites ir valdykite savo projektus."
  - **Forma:**
    - El. pastas * (email input)
    - Slaptazodis * (password input, min 6 simboliai)
    - Pakartokite slaptazodi * (password input)
    - „Registruotis" mygtukas (green, full-width)
  - **Sekmés busena** (display: none -> block po registracijos):
    - Zalias fonas su tekstu: „Registracija sekminga! Patikrinkite savo el. pasta ir patvirtinkite paskyra."
  - **Klaidos pranesimas:** raudona zona
  - **Nuorodos:**
    - „Jau turite paskyra? Prisijungti"
    - „Grizti i pradzia"

---

## 4. Komponentu biblioteka

### Header (sticky)
- 2 busenos: transparent (hero) + scrolled (baltas su blur)
- Logo (36px) + nav links + auth buttons + hamburger (mobile)
- Transparent: baltas tekstas, baltos nav nuorodos
- Scrolled: tamsus tekstas, pilkos nav nuorodos, seselis

### Mygtukai
| Tipas | Fonas | Tekstas | Hover |
|-------|-------|---------|-------|
| Primary | `--vp-primary` | baltas | tamsi zalia + pakyla -1px + seselis |
| Secondary | baltas 10% + blur | baltas | baltas 18% |
| Outline | transparent | `--vp-primary` | uzpildomas zaliu + baltas tekstas |
| Ghost | transparent | `--vp-primary` | primary-mist fonas |
| Green | `--vp-primary` | baltas | primary-dark + seselis |
| Accent | `--vp-accent` | baltas | accent-light + glow |
| SM variant | mazesnis padding (10px 20px), 14px sriftas, 40px min-height |

### Korteles (`vp-card`)
- Baltas fonas, pilkas border, radius 20px
- Padding: 36px 32px
- Hover: pakyla -4px, didelis seselis, virsutinis gradient bar (green->gold, scaleX animacija)
- SVG ikona (56x56) su gradiento fonu

### Nuotrauku korteles (`vp-photo-card`)
- 4:3 aspect ratio, radius 12px, border
- Lazy loading su placeholder (pulse animacija)
- Hover overlay (gradient nuo juodo apacioje)
- Featured badge (auksinis) + Location badge (baltas)

### Section header
- Label (uppercase, 12px, auksine spalva, 0.08em letter-spacing)
- H2 (40px desktop, 32px tablet, 26px mobile, bold, -0.02em letter-spacing)
- P (17px, secondary spalva)
- Centruotas, max-width 640px, margin-bottom 60px

### Trust bar
- Horizontalus flex su 32px tarpais
- Kiekvienas elementas: ikona (38x38, stiklo efektas) + tekstas
- Naudojamas hero sekcijoje (baltas tekstas)

### Form elementai
- Input/Select/Textarea: radius 10px, border 1.5px, padding 13px 16px, 15px sriftas
- Hover: primary-light border
- Focus: primary border + 4px rgba seselis
- Select: custom rodykle (SVG)
- Form row: 2 stulpeliu grid (1 stulpelis mobile)
- Messages: success (zalias fonas) / error (raudonas fonas), radius 10px

### Auth korteles
- Max-width 420px, radius 20px, didelis seselis
- Virsutinis gradient bar (3px)
- Brand zona, forma, klaidu zona, nuorodos

### Footer
- Tamsus fonas (#122e1e), baltas/pilkas tekstas
- 4 stulpeliu grid (1.5fr 1fr 1fr 1fr)
- Apatine juosta su copyright

### Mobile sticky bar
- Fiksuotas apacioje (< 768px)
- Baltas fonas, border-top, seselis
- 2 flex mygtukai: Skambinti + CTA

---

## 5. Responsive breakpoints

| Breakpoint | Aprasymas |
|------------|-----------|
| > 968px | **Desktop** — pilnas layout, 3-4 stulpeliu grid'ai, horizontali navigacija |
| 769-968px | **Tablet** — 2 stulpeliu grid'ai, mazesni tarpai (72px sekcijos), hero 38px H1 |
| 481-768px | **Mobile** — hamburger meniu, 1 stulpelis, sticky bottom bar, 32px H1 |
| < 480px | **Mazas mobile** — 1 stulpelis, maziausi tarpai (56px), 28px H1, 16px padding |

**Mobile specifika:**
- Nav + auth mygtukai: paslepiami, hamburger meniu
- Hamburger: 3 linijos -> X animacija, full-screen overlay su blur
- Sticky bottom bar: 2 mygtukai (Skambinti + Gauti pasiulyma)
- Touch target'ai: min 48px (mygtukai), min 44px (nav links)
- Form input'ai: 16px sriftas (iOS zoom prevencija)
- Lightbox slider: 280px aukstis (nuo 600px desktop)
- Proceso zingsniai: vertikalus (vietoj horizontaliu)

---

## 6. Interaktyvus elementai

### Sticky Header
- Transparent -> scrolled (po 60px scroll)
- Smooth transition: background 0.35s, box-shadow 0.35s
- Z-index: 200

### Hamburger meniu
- Toggle: 3 linijos <-> X (CSS transformacijos)
- Overlay: pilno ekrano, blur 20px, centruoti links
- Uzdaro paspaudus ant nuorodos

### Smooth scroll
- Anchor links (#paslaugos, #kainos...) scrollina su offset (header aukstis + 16px)

### Fade-in animacijos
- `.vp-fade` elementai atsiranda scroll metu (IntersectionObserver, threshold 0.1)
- Animacija: opacity 0 + translateY(28px) -> visible (0.7s cubic-bezier)

### Before/After Lightbox
- Atidaromas paspaudus nuotrauku kortele
- Mouse + touch drag interakcija
- Escape klavisas uzdaro
- Click uz turinio uzdaro

### Lead forma
- Client-side validacija (required, tel pattern)
- Submit -> POST /api/v1/call-requests
- Success: zalia zona + formos reset
- Error: raudona zona su pranesimus
- Loading state: mygtukas disabled + „Siunciama..."

---

## 7. User flows

### Naujas lankytojas (konversija):
```
Landing (hero) -> Scroll per sekcijas -> „Gauti pasiulyma" ->
Lead forma (vardas + tel) -> Submit -> Sekmé pranesimas
```

### Naujas lankytojas (registracija):
```
Landing -> „Registruotis" (header) -> Register puslapis ->
Uzpildo forma -> El. pasto patvirtinimas -> Login -> Kliento portalas
```

### Galerijos lankytojas:
```
Landing -> „Ziureti darbu pokycius" arba footer „Galerija" ->
Gallery -> Filtruoja pagal lokacija -> Paspaudzia kortele ->
Lightbox (before/after slider) -> Uzdaro -> Tesia narstima
```

### Grizimas prisijungti:
```
Landing -> „Prisijungti" (header) -> Login puslapis ->
El. pastas + slaptazodis -> Kliento portalas (#/)
```

---

## 8. Deliverables (ko tikimasi is dizainerio)

1. **Komponentu biblioteka** Figma'oje:
   - Header (2 busenos: transparent + scrolled)
   - Mygtukai (6 variantai + SM)
   - Korteles (vp-card, photo-card, pricing-card, trust-card, auth-card)
   - Form elementai (input, select, textarea, form-row)
   - Section headers (label + H2 + P)
   - Badge/pill (featured, location, status)
   - Trust bar items
   - Footer
   - Mobile sticky bar

2. **4 desktop ekranai:**
   - Landing (pilnas, su visomis 7 sekcijomis)
   - Gallery (hero + filtrai + grid + lightbox overlay)
   - Login
   - Register (+ success state)

3. **4 mobile ekranai** (tie patys, adaptuoti):
   - Landing mobile (hamburger, 1 stulpelis, sticky bar)
   - Gallery mobile (1 stulpelio grid, mazesnis hero)
   - Login mobile
   - Register mobile

4. **Interaktyvus elementai:**
   - Lightbox (before/after slider su rankena)
   - Hamburger meniu (open/close busenos)
   - Header (transparent -> scrolled busenos)
   - Lead forma (normal, loading, success, error busenos)

5. **Prototype:**
   - Landing scroll -> CTA -> Lead forma submit
   - Landing -> Gallery -> Filter -> Lightbox
   - Landing -> Login -> (redirect)

---

## 9. Prioritetu eile dizaineriui

| Prioritetas | Ekranas | Kodel |
|-------------|---------|-------|
| P1 | Landing (desktop + mobile) | Pagrindinis konversijos puslapis, pirmasis ispudis |
| P1 | Gallery + Lightbox | Irodymu puslapis, parodo darbu kokybe |
| P2 | Login + Register | Auth flow, butinas funkcionalumui |
| P2 | Komponentu biblioteka | Daugkartinis panaudojimas visuose ekranuose |
| P3 | Header busenos + animacijos | Polish, UX detalés |
