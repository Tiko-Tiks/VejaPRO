# Sklypio vertinimo kainos logine grandine (V3 — įgyvendinta)

**Atnaujinta: 2026-02-22.** V3 kontraktas ir out-of-order apsauga įgyvendinti pagal planą.

---

## Dabartine grandine (V3 — kaip veikia)

1. **Žingsnis 1 — Paslauga ir metodas**
   - Klientas pasirenka: Vejos įrengimas (sėjimas / ruloninė / hidroseija) arba Apleisto sklypo tvarkymas (mažas / vidutinis / didelis).
   - Tai nustato bazinį tarifą (EUR/m²) pagal `estimate_rules.py` (pakopos pagal plotą).

2. **Žingsnis 2 — Objekto informacija**
   - Sklypo plotas (m²) ir objekto adresas (atstumui skaičiuoti). Naudojama `s.baseRange` (service, method, area_m2, km_one_way).

3. **Žingsnis 3 — Kontaktai ir skaičiavimas**
   - Telefonas (privaloma), pastabos (neprivaloma). El. paštas **neklausiamas** — naudojamas tik `current_user.email`.
   - Sistema skaičiuoja atstumą, tada kviečia `POST /api/v1/client/estimate/price` su V3 payload: `rules_version`, `service`, `method`, `area_m2`, `km_one_way`, `addons_selected: []`.
   - Atsakymas įrašomas į `s.priceResult`; pereinama į 4 žingsnį.

4. **Žingsnis 4 — Kaina ir priedai**
   - **Kaina rodoma tik iš `s.priceResult`** (vienintelis šaltinis — serverio atsakymas). Kainos kortelė turi fiksuotą konteinerį `estPriceCard`.
   - Priedai: kurie turi `pricing_mode: "included_in_estimate"` (iš `GET /client/estimate/rules` addons) — pasirinkimas atnaujina `s.selectedAddons` ir iškart kviečia perskaičiavimą (`repriceEstimate`). Kiti priedai — tik į pastabas (request_only).
   - **Out-of-order apsauga:** `AbortController` + `priceSeq`; atnaujinamas tik paskutinio užklausos atsakymas. Submit mygtukas disabled kol `s.isPricing === true`.
   - **409 (pasenęs rules_version):** refresh rules, pakartoti /price (arba po submit — reprice ir pranešti). UI rodo, kad kaina perskaičiuota.
   - **Pirmo vizito laikas:** `GET /api/v1/client/schedule/available-slots` (jei `ENABLE_SCHEDULE_ENGINE`); pasirinktas slotas siunčiamas kaip `preferred_slot_start`. Vėlesnius vizitus priskirs admin.

5. **Pateikimas**
   - Submit payload naudoja **tą patį** `s.selectedAddons` (surūšiuotas kaip `addons_selected`), ne skaitymą iš DOM. Backend perskaičiuoja kainą, įrašo `addons_selected` ir `price_result` į `client_info.estimate`, atsakyme grąžina `price_result`. El. paštas tik iš `current_user.email`.

---

## Kas buvo pataisyta (santrauka)

- **Vienas šaltinis tiesos:** 4 žingsnio kaina tik iš `POST /client/estimate/price` atsakymo (`s.priceResult`); submit `addons_selected` tik iš `s.selectedAddons`.
- **Out-of-order apsauga:** AbortController + priceSeq — greitas on/off/on neperrašo kainos senu atsakymu.
- **V3 kontraktas:** `rules_version`, `base_range` (service, method, area_m2, km_one_way), `addons_selected[]`. Legacy `mole_net: bool` palaikomas normalizacijoje (→ addons_selected). Nežinomas addon → 400.
- **Priedai iš rules:** `pricing_mode: "included_in_estimate" | "request_only"` — FE nekoduoja, kurie priedai keičia kainą.
- **El. paštas:** Kliento portale neklausiamas; serveris naudoja tik `current_user.email`.

---

## Techniniai failai

- **Kaina (backend):** `backend/app/services/estimate_rules.py` — `compute_price()`, `get_rate()`, `get_rules()` (addons su `pricing_mode`), `get_valid_addon_keys()`.
- **API:** `backend/app/api/v1/client_views.py` — `POST /client/estimate/price`, `POST /client/estimate/submit` (normalizacija, 400 unknown addon, `price_result` atsakyme), `GET /client/schedule/available-slots`.
- **Schemas:** `backend/app/schemas/client_views.py` — `BaseRangeSchema`, `EstimatePriceRequest`/`EstimateSubmitRequest` su `addons_selected`, `EstimateSubmitResponse.price_result`.
- **UI (vedlys):** `backend/app/static/client.html` — state (`priceResult`, `selectedAddons`, `isPricing`, `priceAbort`, `priceSeq`), `refreshPriceFromExtras()`, submit iš state.
- **Dokumentacija:** `backend/docs/CLIENT_UI_V3.md`, `backend/API_ENDPOINTS_CATALOG.md` (§ 2.8, available-slots).

---

*V3 įgyvendinimas užtikrina, kad matoma kaina = patvirtinta kaina; klientas gauna preliminarų vertinimą ir gali pasirinkti pirmo vizito laiką be perteklinio apkrovimo.*
