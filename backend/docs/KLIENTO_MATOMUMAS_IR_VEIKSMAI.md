# Ką mato klientas ir kokius veiksmus atlieka (sąsaja su admin)

Šis dokumentas aprašo **kliento portalo** turinį ir veiksmus bei kaip jie susiję su **admin** pusėje (kliento kortelė, planuotojas, projekto diena). Viskas susieta — kliento veiksmai atsispindi admin sąsajoje.

**Kliento portalas:** `vejapro.lt/client` (JWT, magic link arba Supabase login).  
**Admin kliento kortelė:** `/admin/client/{client_key}` — vieno kliento visų projektų ir veiksmų vaizdas.

---

## 1. Ką klientas mato

### 1.1 Dashboard (`#/`)

**Šaltinis:** `GET /api/v1/client/dashboard`

| Blokas | Turinys |
|--------|---------|
| **Reikia jūsų veiksmo** | Kortelės projektams, kuriuose reikia kliento žingsnio: statusas, „Kitas žingsnis“ tekstas, pagrindinis CTA (pvz. „Apmokėti depozitą“, „Pasirašyti sutartį“, „Patvirtinti priėmimą“). |
| **Mano projektai** | Kortelių sąrašas: pavadinimas, statusas (Juodraštis / Avansas gautas / …), santrauka, dokumentai, mygtukas „Atidaryti projektą“. |
| **Papildomos paslaugos** | Upsell kortelės (3–6) — pavadinimas, kaina, „Užsakyti“. |

Jei projektų nėra: „Projektų dar nėra. Pradėkite nuo įvertinimo.“ + CTA į įvertinimo vedlį.

---

### 1.2 Mano projektai (`#/projects`)

Tas pats projektų sąrašas kaip dashboard (kortelės su statusu, santrauka, „Atidaryti“).

---

### 1.3 Projekto detalės (`#/projects/{id}`)

**Šaltinis:** `GET /api/v1/client/projects/{id}/view`

| Sekcija | Ką mato klientas |
|---------|-------------------|
| **Būsena** | Statuso pill (Juodraštis, Avansas gautas, Suplanuota, Laukiama eksperto, Sertifikuota, Aktyvus), status_hint, „Kitas žingsnis“ tekstas. |
| **Pagrindinis CTA** | Vienas mygtukas pagal būseną (žr. lentelę skyriuje 2). |
| **Papildomi veiksmai** | Iki 2 antriniai mygtukai (secondary_actions). |
| **Timeline** | 6 žingsniai: Juodraštis → Avansas gautas → Suplanuota → Laukiama eksperto → Sertifikuota → Aktyvus (dabartinis paryškintas). |
| **Dokumentai** | Sąrašas pagal būseną: preliminari sąmata, avansinė sąskaita, sutartis, grafikas, sertifikatas, galutinė sąskaita, garantinis. Kiekvienas su mygtuku „Peržiūrėti“. |
| **Mokėjimų santrauka** | Depozitas: APMOKĖTAS / LAUKIAMA; Galutinis: APMOKĖTAS / LAUKIAMA; „Kitas žingsnis“ tekstas. |
| **Vizitai** | `visits[]`: PRIMARY / SECONDARY, statusas (CONFIRMED, HELD, NONE), data, label. |
| **Antro vizito laikas** | Jei `can_request_secondary_slot=true` ir dar nepateiktas — slot picker (laisvi laikai iš `GET /api/v1/client/schedule/available-slots`) + „Kitas laikas“. Jei jau pateiktas — rodomas pasirinktas laikas. |
| **Įvertinimo duomenys** | Jei yra — paslauga, metodas, plotas, adresas, atstumas, kaina, priedai, pastabos (tik peržiūrai). |

---

### 1.4 Įvertinimo vedlys (`#/estimate`)

**Šaltinis:** `GET /api/v1/client/estimate/rules`, `POST .../analyze`, `POST .../price`, `POST .../submit`

| Žingsnis | Ką mato klientas |
|----------|-------------------|
| 1 | Paslaugos ir metodo pasirinkimas, plotas (m²). |
| 2 | Adresas, atstumas (skaičiuojamas arba rankinis), nuotraukų įkėlimas (optional). |
| 3 | Priedų pasirinkimas (iš taisyklių; kainą keičiantys — „included_in_estimate“, kiti — „request_only“). |
| 4 | Laisvų laikų pirmam vizitui pasirinkimas (`available-slots`), jei įjungtas Schedule Engine. |
| 5 | Kainos santrauka (iš `POST .../price`), kontaktai (telefonas, adresas — email iš JWT), mygtukas „Pateikti užklausą“. |

Po pateikimo: sukuriamas **DRAFT** projektas su `client_info.estimate` (addons_selected, price_result, preferred_slot_start ir kt.).

---

### 1.5 Papildomos paslaugos (`#/services`)

**Šaltinis:** `GET /api/v1/client/services/catalog`, `POST /api/v1/client/services/request`

Katalogas (3–6 kortelių); klientas pasirenka ir pateikia užklausą. Sukuriamas **service_requests** įrašas (NEW). Admin vėliau gali peržiūrėti ir atlikti veiksmus (ne kliento kortelėje, bet susieta su projektu).

---

## 2. Kokius veiksmus atlieka klientas

Visos šios veiksmos yra susietos su projektu; admin mato rezultatą kliento kortelėje arba planuotoje / projekto dienoje.

| Veiksmas | Kada rodomas | API / rezultatas | Ką mato admin |
|----------|----------------|------------------|----------------|
| **Pateikti įvertinimą** | Įvertinimo vedlys, 5 žingsnis | `POST /api/v1/client/estimate/submit` → sukuria DRAFT, `client_info.estimate` | Kliento kortelėje atsiranda naujas (arba atnaujintas) projektas; Summary „Stadija” = DRAFT; įvertinimo duomenys bloke „Projektai“ → Įvertinimas. |
| **Pasirinkti pirmo vizito laiką** | Įvertinimas, 4 žingsnis | Submit palaiko `preferred_slot_start` | Admin mato pageidavimą; planuotojas / dienos planas — vizitai. |
| **Pasirinkti antro vizito laiką** | Projekto detalės, kai `can_request_secondary_slot` | `POST /api/v1/client/projects/{id}/preferred-secondary-slot` | Išsaugoma `client_info.preferred_secondary_slot`; audit SECONDARY_SLOT_REQUESTED. Admin mato kliento kortelėje / vizituose. |
| **Atidaryti projektą** | Dashboard / Mano projektai | Navigacija į `#/projects/{id}` | — |
| **Peržiūrėti įvertinimą** | DRAFT, quote_pending | UI rodo įvertinimo duomenis | Admin kortelėje mato tą patį įvertinimą. |
| **Apmokėti depozitą** | DRAFT, depozitas laukiamas | `POST /api/v1/client/actions/pay-deposit` → grąžina pranešimą „Susisiekite dėl avanso“ | Klientas negali pats pakeisti statuso. Admin įrašo depozitą (manual arba Stripe) → pereinama į PAID. Kortelėje: „Depozitas“ → Gauta. |
| **Pasirašyti sutartį** | PAID | `POST /api/v1/client/actions/sign-contract` → grąžina sutarties URL | Admin gali matyti sutarties dokumentą; contract_signed nustatomas admin pusėje. |
| **Peržiūrėti grafiką** | PAID+ | Dokumentų sąraše „Peržiūrėti“ | Admin mato tą patį grafiką projekto dienoje / dokumentuose. |
| **Mokėti likutį** | CERTIFIED, galutinis laukiamas | `POST /api/v1/client/actions/pay-final` → pranešimas | Kaip ir depozitas — mokėjimą įrašo admin. Po FINAL įrašo galima siųsti kliento patvirtinimą (email). |
| **Patvirtinti priėmimą** | CERTIFIED, galutinis apmokėtas, laukiama patvirtinimo | `POST /api/v1/client/actions/confirm-acceptance` → „Patvirtinimo nuoroda išsiųsta el. paštu“ | Backend gali siųsti patvirtinimo nuorodą; klientas spustelėja nuorodą → CERTIFIED → ACTIVE. Admin kortelėje statusas → ACTIVE. |
| **Užsakyti papildomą paslaugą** | Bet kur | `POST /api/v1/client/services/request` | service_requests įrašas; admin gali matyti / tvarkyti papildomas paslaugas (ne būtinai kliento kortelėje, bet susieta su projektais). |
| **Redaguoti juodraštį** | DRAFT | `PUT /api/v1/client/projects/{id}/draft` | Pakeitimai atsispindi projekte; admin kortelėje mato atnaujintus duomenis. |

---

## 3. Ryšys su admin (kliento kortelė ir planuotojas)

- **Kliento kortelė** (`/admin/client/{client_key}`) rodo tą patį klientą (identifikuotą pagal `client_key`), jo projektus, mokėjimus, vizitus, dokumentus, AI kainą, vietos apklausą, skambučius, nuotraukas, timeline. Viskas, ką klientas pateikė ar atliko, čia atsiranda (įvertinimas, vizitų laikai, mokėjimų būsenos, patvirtinimas).
- **Planuotojas** (`/admin`) rodo dienų planą ir „Reikia žmogaus“ darbus; vizitai ir užduotys susieti su tais pačiais projektais.
- **Projekto diena** (`/admin/project/{id}`) — vieno projekto dienos vaizdas; čia admin atlieka check-in, užbaigimą, įkelia nuotraukas, mato dokumentus. Kliento pateikti duomenys (įvertinimas, vizitų laikai) naudojami planuojant ir dirbant.

Santrauka:

- Klientas **pateikia įvertinimą** → admin mato DRAFT ir įvertinimą kliento kortelėje ir gali generuoti AI kainą, planuoti vizitus.
- Klientas **pasirenka vizitų laikus** → admin mato planuotoje / vizituose.
- Klientas **„Apmoka depozitą“** (susisiekia) → admin įrašo mokėjimą → PAID; kortelėje Depozitas = Gauta.
- Klientas **„Moka likutį“** (susisiekia) → admin įrašo FINAL → galima siųsti patvirtinimo nuorodą.
- Klientas **patvirtina priėmimą** (nuoroda el. paštu) → CERTIFIED → ACTIVE; admin mato ACTIVE ir užbaigtą procesą.

Taip kliento matomumas ir veiksmai neatsilieka nuo admin: vienas šaltinis tiesos (projektas, mokėjimai, vizitai, dokumentai), o admin sąsaja rodo tą patį, ką klientas mato ir ką jis atliko.
