# VejaPRO — AI įdiegimo rekomendacija

Trumpa gairė, **kurį AI** naudoti ir **kokiai platformos daliai**, kad geriausiai atitiktų lūkesčius (greitas atsakas, lietuviška kalba, maža kaina, saugumas).

---

## 1. Platformos AI poreikiai (prioritetu)

| Poreikis | Kas jau yra | Ko trūksta | Kritiškumas |
|----------|--------------|------------|--------------|
| **Nuotraukų analizė (sklypas)** | `vision_service.py` — mock, `ENABLE_VISION_AI` | Tikras vaizdo modelis: plotas, kliūtys, reljefas, `confidence` | Vidutinis (nice-to-have) |
| **Dokumentų ekstrakcija (sąskaitos/kvitai)** | Finance: upload + extract; dabar tik vendor rules (filename) | LLM: iš PDF/vaizdo ištraukti sumą, datą, tiekėją → ledger | Aukštas (darbas sutaupo laiko) |
| **Kalbos / intent (skambučiai, chat)** | Schedule Engine: laiko pasiūlymas, HELD | Galima vėliau: AI intent („noriu atidėti“, „atšaukti“) | Žemas (galima rule-based) |

---

## 2. Kuris AI geriausiai atitinka platformą

### A. Vaizdo analizė (sklypo nuotraukos — Vision)

Reikia **vision-capable** modelio (nuotrauka → JSON: plotas, kliūtys, confidence).

| Tiekėjas | Modelis | Privalumai | Trūkumai | Atitikimas |
|----------|---------|------------|----------|------------|
| **Anthropic Claude** | Claude 3.5 Sonnet (vision) | Labai gera vaizdo + teksto supratimas, gerai laikosi JSON, LT kalba | Brangiau, API limitai | **Geriausias atitikimas** |
| **OpenAI** | GPT-4o / GPT-4o mini | Greitas, geras vision, gerai žinomas API | Kaina, priklausomybė nuo vieno tiekėjo | **Labai geras** |
| **Groq** | Llama 3.2 90B Vision (kai pilnai) | Labai greitas, pigus | Vision palaikymas ir LT kokybė dar kintami | **Gerai, jei prioritetas — greitis/kaina** |
| **Google** | Gemini 1.5 Pro / Flash | Vision + ilgas kontekstas | Daugiau setup, mažiau naudojama stack'e | Alternatyva |

**Rekomendacija Vision:**  
- **Pirmas pasirinkimas:** **Claude 3.5 Sonnet (vision)** — geriausias balansas tarp kokybės, JSON struktūros ir lietuviškos kalbos.  
- **Alternatyva (greitis/kaina):** **GPT-4o mini** arba **Groq** (kai vision stabilus) — jei svarbiau latency ir cost.

---

### B. Dokumentų ekstrakcija (sąskaitos, kvitai → ledger)

Reikia **teksto/PDF** (arba vaizdo kvito) → struktūruotas JSON: suma, valiuta, data, tiekėjas, kategorija.

| Tiekėjas | Modelis | Privalumai | Trūkumai | Atitikimas |
|----------|---------|------------|----------|------------|
| **Anthropic Claude** | Claude 3.5 Haiku / Sonnet | Puikūs structured output, LT, pigesnis Haiku | — | **Labai geras** |
| **OpenAI** | GPT-4o mini | Greitas, structured output, gerai žinomas | Kaina | **Labai geras** |
| **Groq** | Llama 3.1 70B / 8B | Labai greitas ir pigus | Mažiau „disciplinuotas“ JSON, LT gali reikėti prompt inžinerijos | **Geras jei prioritetas — kaina** |

**Rekomendacija dokumentams:**  
- **Pirmas pasirinkimas:** **Claude 3.5 Haiku** — greitas, pakankamai geras ekstrakcijai, mažesnė kaina nei Sonnet.  
- **Alternatyva:** **Groq (Llama 3.1 70B)** — jei norima minimalizuoti kainą ir prioritetas greičiui.

---

### C. Bendras atitikimas platformos lūkesčiams

- **Lietuviška kalba:** Claude ir OpenAI abu gerai atitinka; Groq priimtinas, bet gali reikėti aiškių pavyzdžių prompte.
- **Greitas atsakas (UX):** Groq > OpenAI (4o mini) > Claude; vision užklausoms paprastai 2–5 s priimtina.
- **Saugumas (AI nekeičia statusų):** Viską valdo tavo logika (kaip dabar) — AI tik grąžina duomenis; sprendimus daro tik tavo backend (transition_service, audit).
- **Kaina:** Groq pigiausias, tada Claude Haiku / OpenAI mini, brangiausias — Claude Sonnet / GPT-4o.

---

## 3. Konkretus pasirinkimas pagal tikslą

**Jei nori vieno tiekėjo (paprastesnė integracija):**  
→ **Anthropic Claude** (vision: 3.5 Sonnet, dokumentams: 3.5 Haiku).  
Geriausias balansas kokybė / LT kalba / structured output.

**Jei prioritetas — greitis ir maža kaina:**  
→ **Groq** (vision: kai bus stabilus Llama 3.2 Vision, dokumentams: Llama 3.1 70B).  
Jau minimas techninėje dokumentacijoje (LangChain + Groq).

**Jei jau naudoji OpenAI kitur:**  
→ **OpenAI** (GPT-4o mini dokumentams, GPT-4o vision sklypams).  
Vienoda ekosistema, geri rezultatai.

---

## 4. Įgyvendinimo eiliškumas

1. **Dokumentų ekstrakcija (Finance)**  
   Pridėti tikrą LLM į `extract_document`: PDF/vaizdo tekstas → LLM su promptu (suma, data, tiekėjas, kategorija) → `extracted_json`.  
   Rekomenduojamas modelis: **Claude 3.5 Haiku** arba **Groq Llama 3.1 70B**.

2. **Vision (sklypo nuotraukos)**  
   Pakeisti `vision_service.analyze_site_photo()` iš mock į tikrą vision API (nuotrauka → JSON su area_estimate_m2, obstacles, terrain_quality, confidence).  
   Rekomenduojamas modelis: **Claude 3.5 Sonnet (vision)** arba **GPT-4o mini**.

3. **Call/Chat intent (vėliau)**  
   Jei reikės AI: intent recognition iš teksto → taisyklės (pvz. „atidėti“ → schedule flow). Galima tą pačią Claude Haiku arba Groq naudoti.

---

## 5. Techninės pastabos

- **Feature flags:** `ENABLE_VISION_AI` ir `ENABLE_FINANCE_AI_INGEST` jau yra; AI kvietimus darome tik kai atitinkamas flag įjungtas.
- **Audit ir saugumas:** AI atsakymai nėra tiesiogiai rašomi į statusus; visada per tavo validaciją ir audit log.
- **Klaidos:** Jei AI nepavyksta ar grąžina nevalidų JSON — fallback į dabartinį elgesį (rules/stub), ne breaking.
- **Lietuviška:** Promptuose aiškiai nurodyti „Respond only in JSON“ ir pateikti pavyzdžius lietuviškais laukų pavadinimais, jei reikia.

---

**Santrauka:** Platformos lūkesčiams geriausiai atitinka **Claude (Anthropic)** — vision ir dokumentams; jei prioritetas kaina/greitis — **Groq**. Pirmiausia verta įdiegti **dokumentų ekstrakciją** (Finance), paskui **Vision** (sklypų nuotraukos).

