# Kliento kortelė — aprašymas ir specifikacija

Šis dokumentas aprašo **kliento kortelės** (`/admin/client/{client_key}`) struktūrą: rodinius, duomenų šaltinius, veiksmus ir susijusius API. Naudoti planuojant dizaino pakeitimus arba naujų funkcijų įgyvendinimą.

**Puslapis:** `/admin/client/{client_key}` (Admin Ops V1)  
**Feature flag:** `ENABLE_ADMIN_OPS_V1`  
**Teisės:** Admin rolė (prisijungęs administratorius)

---

## Turinys

1. [Puslapio viršus ir navigacija](#1-puslapio-viršus-ir-navigacija)
2. [Summary (suvestinė)](#2-summary-suvestinė)
3. [AI kainų pasiūlymas](#3-ai-kainų-pasiūlymas)
4. [Vietos anketa](#4-vietos-anketa)
5. [Projektai](#5-projektai)
6. [Skambučiai ir laiškai](#6-skambučiai-ir-laiškai)
7. [Mokėjimai](#7-mokėjimai)
8. [Nuotraukos](#8-nuotraukos)
9. [Timeline](#9-timeline)
10. [Modalas: Koreguoti kainą](#10-modalas-koreguoti-kainą)
11. [API nuorodos](#11-api-nuorodos)
12. [Galimi pakeitimai (dizainas / UX)](#12-galimi-pakeitimai)

---

## 1. Puslapio viršus ir navigacija

| Elementas | Aprašymas |
|-----------|------------|
| **Antraštė** | Rodomas `summary.display_name` arba fallback „Kliento kortelė“. |
| **← Planner** | Nuoroda atgal į planner: `/admin`. |
| **Generuoti** | Sukuria AI kainų pasiūlymą. Matomas tik jei `ENABLE_AI_PRICING=true`. |
| **Patvirtinti** | Patvirtina AI kainą. Aktyvus tik kai: status „ok“, nėra sprendimo, yra fingerprint. |
| **Koreguoti** | Atidaro modalą — nauja kaina + priežastis. |
| **Ignoruoti** | Pažymi AI pasiūlymą kaip ignoruotą (be kainos keitimo). |

**Duomenų šaltinis:** antraštė iš `GET …/card` → `summary.display_name`.

---

## 2. Summary (suvestinė)

**Tipas:** 4 stulpelių grid + attention flags (badge'ai).

| Laukas | Šaltinis / reikšmė |
|--------|---------------------|
| **Stadija** | Pirmo projekto `status` (DRAFT, PAID, SCHEDULED, …) — status pill. |
| **Depozitas** | Pirmo projekto `deposit_state` (pvz. „Reikia įrašyti“, „Gauta“). |
| **Kitas vizitas** | Artimiausio ne atšaukto vizito data (iš appointments). |
| **Uždirbta** | `summary.earned_total` (EUR). |
| **Attention flags** | Badge'ai pagal `summary.attention_flags` (pvz. NEEDS_DEPOSIT). Jei nėra — „Įspėjimų nėra“. |

**Duomenų šaltinis:** `GET …/client/{client_key}/card` → `summary`.

---

## 3. AI kainų pasiūlymas

**Sąlyga:** rodoma tik jei `ENABLE_AI_PRICING=true`.

| Elementas | Aprašymas |
|-----------|------------|
| **Status eilutė** | Confidence pill (GREEN/YELLOW/RED), status (ok/fallback), projekto ID (trumpas), fingerprint (pirmi 12 simbolių). |
| **Sprendimo badge** | Jei sprendimas jau priimtas: „Sprendimas: Patvirtinta / Koreguota / Ignoruota“, su suma, priežastimi ir data. |
| **Fallback eilutė** | Kai status „fallback“ — pranešimas, kad patvirtinti negalima; galima tik ignoruoti arba koreguoti rankiniu būdu. |
| **Grid (6 langeliai)** | Bazinė kaina, AI korekcija, Final pasiūlymas (paryškintas), Kainos rezis (min–max), Confidence (pill + skaičius), Susiję projektai (skaičius). |
| **Reasoning** | Teksto blokas (italic, pilkas). |
| **Faktoriai** | Etiketės: nuolydžio korekcija, dirvos paruošimas, augmenijos valymas, priejimo sudėtingumas, atstumo antkainis, kliūčių šalinimas, laistymo nuolaida, sezoninė paklausa. |
| **Timestamp** | Kada sugeneruota (mažu šriftu). |

**Veiksmai:** Generuoti, Patvirtinti, Koreguoti, Ignoruoti (žr. skyrių 1).  
**Duomenų šaltinis:** `card` payload → `ai_pricing`, `ai_pricing_meta`, `ai_pricing_decision`, `pricing_project_id`.

---

## 4. Vietos anketa

**Tipas:** `<details>` (collapse). Naudojama AI kainai (plotas, nuolydis, augalija ir kt.).

| Laukas | Tipas | Reikšmės / validacija |
|--------|--------|------------------------|
| Dirvožemis | select | UNKNOWN, SAND, CLAY, LOAM, PEAT |
| Nuolydis | select | FLAT, GENTLE, MODERATE, STEEP |
| Augalija | select | BARE, SPARSE_GRASS, DENSE_GRASS, WEEDS, MIXED |
| Priejimas technikai | select | EASY, RESTRICTED, DIFFICULT |
| Atstumas (km) | number | — |
| Yra laistymo sistema | checkbox | — |
| Kliūtys | checkboxes | Medžiai, Tvora, Komunikacijos, Trinkelės, Nuolydis, Drenažas, Kita |
| **Išsaugoti** | mygtukas | Siunčia į `PUT …/pricing/{project_id}/survey` |

**API:** `PUT /api/v1/admin/pricing/{project_id}/survey` (extended_survey JSON).

---

## 5. Projektai

Kiekvienas kliento projektas — **expandable** eilutė (`<details class="project-expand-row">`).

**Summary eilutė (uždaryta):**
- Trumpas projekto ID (pirmi 8 simboliai, mono).
- Status pill.
- Depozitas / Galutinis (`deposit_state` / `final_state`).
- Plotas (`area_m2`), jei yra.
- Nuoroda **„Atidaryti“** → `/admin/project/{id}`.

**Atidarius — subsekcijos:**

| Subsekcija | Turinys |
|------------|---------|
| **Įvertinimas** | Lentelė: Paslauga, Metodas, Plotas, Adresas, Telefonas, Atstumas, Kaina, Pageidaujamas laikas, Priedai, Pastabos. |
| **Mokėjimai** | Depozitas (state + suma), Galutinis (state + suma), Kitas žingsnis (tekstas). |
| **Dokumentai** | Mygtukai su nuorodomis (label / type). |
| **Vizitai** | Lentelė: Tipas, Statusas, Data. |
| **Išlaidos** | Tik jei `ENABLE_FINANCE_LEDGER` — kategorijos ir sumos, viso. |

**Veiksmai:** nuoroda „Atidaryti“ į projekto dienos puslapį.  
**Duomenų šaltinis:** `card` → `projects[]`.

---

## 6. Skambučiai ir laiškai

**Tipas:** lentelė (collapse).

| Stulpelis | Aprašymas |
|-----------|------------|
| ID | Trumpas identifikatorius. |
| Statusas | Skambučio / užklausos būsena. |
| Šaltinis | Iš kur (pvz. Call Assistant). |
| Kontaktas | Maskuotas (PII apsauga). |
| Data | — |

**Kai įrašų nėra arba modulis išjungtas:** „Skambučių ir laiškų istorijos nerasta arba modulis išjungtas.“  
**Veiksmai:** tik peržiūra.  
**Duomenų šaltinis:** `card` → `call_requests` (Call Assistant).

---

## 7. Mokėjimai

**Tipas:** lentelė (collapse).

| Stulpelis | Aprašymas |
|-----------|------------|
| Projektas | Trumpas `project_id`. |
| Tipas | Pvz. DEPOSIT, FINAL. |
| Suma | — |
| Statusas | — |
| Data | `received_at`. |

**Kai įrašų nėra:** „Mokėjimų nerasta.“  
**Veiksmai:** tik peržiūra.  
**Duomenų šaltinis:** `card` → `payments` arba atitinkami laukai projekte.

---

## 8. Nuotraukos

**Tipas:** kortelių grid (collapse). Kiekvienoje kortelėje: kategorija, trumpas `project_id`, nuotrauka (thumbnail/medium/file_url), nuoroda į pilną failą (`target="_blank"`).  
**Veiksmai:** peržiūra ir atidarymas naujame lange.  
**Duomenų šaltinis:** `card` → nuotraukų sąrašas (pvz. per projektus ar atskirą struktūrą).

---

## 9. Timeline

**Tipas:** chronologinis sąrašas (collapse).  
**Stulpeliai / laukai:** Veiksmas (`action`), Data, `actor_type`, `entity_id` (trumpas).  
**Veiksmai:** tik peržiūra.  
**Duomenų šaltinis:** `card` → `timeline` arba audit įrašai.

---

## 10. Modalas: Koreguoti kainą

Atidaromas mygtuku **Koreguoti** (skyrius 1).

| Laukas | Tipas | Validacija |
|--------|--------|------------|
| Nauja kaina (EUR) | number | step 0.01, min 0.01. |
| Priežastis | textarea | min 8 simboliai. |
| **Atsaukti** | mygtukas | Uždaro modalą. |
| **Išsaugoti** | mygtukas | Siunčia į `POST …/pricing/{project_id}/decide` su `action: "edit"`, `adjusted_price`, `reason`. |

**API:** `POST /api/v1/admin/pricing/{project_id}/decide` (action `edit`).

---

## 11. API nuorodos

Visi endpointai reikalauja Admin autentifikacijos.

| Metodas | Kelias | Paskirtis |
|---------|--------|-----------|
| GET | `/api/v1/admin/ops/client/{client_key}/card` | Pilnas kortelės payload: summary, projects, payments, calls, photos, timeline, ai_pricing, extended_survey, feature_flags. |
| POST | `/api/v1/admin/ops/client/{client_key}/proposal-action` | Registruoti „proposal“ veiksmą (skiriasi nuo kainų mygtukų logikos). |
| POST | `/api/v1/admin/pricing/{project_id}/generate` | Sugeneruoti AI kainų pasiūlymą. |
| POST | `/api/v1/admin/pricing/{project_id}/decide` | Patvirtinti / koreguoti / ignoruoti AI kainą (`adjusted_price`, `reason` kur reikia). |
| PUT | `/api/v1/admin/pricing/{project_id}/survey` | Išsaugoti vietos (sklypo) apklausą. |

---

## 12. Galimi pakeitimai (dizainas / UX)

- **Antraštė:** pavadinimo rodymas, mygtukų išdėstymas ir prioritetas.
- **Summary:** laukų rinkinys, pavadinimai lietuviškai, attention flags vaizdas.
- **AI kainų blokas:** informacijos kiekis, išdėstymas (grid vs. kortelės), sprendimo badge ir mygtukų vieta.
- **Vietos anketa:** numatyta atidarymo būsena (atidaryta/closed), grupavimas, etiketės.
- **Projektai:** summary eilutėje daugiau prasmingos informacijos (adresas, data) vietoj trumpo ID; subsekcijų tvarka ir pavadinimai.
- **Skambučiai, mokėjimai, nuotraukos, timeline:** lentelių stilius, stulpelių rinkinys, numatyta collapse būsena.
- **Bendras išdėstymas:** vienos kolonos vs. dviejų stulpelių, sekcijų prioritetų eiliškumas.

Kai nuspręsite, kuriuos blokus keisti (pvz. tik summary + projektai arba tik AI kainos), galima detaliau suplanuoti maketą ir žingsnis po žingsnio pritaikyti prie šios kortelės.
