# Schedule Engine Backlog (V1.1.1)

Data: 2026-02-07
Statusas: Atviras (likusiu darbu sarasas)

Sis dokumentas apima, kas dar liko padaryti, kad Schedule Engine butu uzdarytas kaip pilnai veikiantis end-to-end modulis (ne tik API).

## Kas jau igyvendinta (santrauka)

- Phase 0: `RESCHEDULE` preview/confirm su HMAC hash, `row_version`, `lock_level` saugikliais ir audit.
- Phase 2: `HELD` rezervacijos (Hold API) su `conversation_locks`.
- Phase 3: `Daily batch approve` API + minimalus Admin UI mygtukas kalendoriuje.

Detaliau: `SCHEDULE_ENGINE_V1_SPEC.md`.

## Liko padaryti (prioritetu tvarka)

1. Voice integracija (Twilio)
- Sukurti Twilio voice webhook srauta, kuris realiai kviecia Hold API (create -> confirm/cancel).
- Konfliktu valdymas: jei slotas uzimtas (409) siulyti kita.
- Idempotency: naudoti `call_sid` / `event_sid` kaip idempotency raktus (jei dar nenaudojama).

2. Web chat integracija
- Sukurti chat event handler'i, kuris naudoja ta pati Hold API ir RESCHEDULE API.
- Concurrency taisykle: vienas klientas vienu metu (lock per conversation/client).

3. Hold expiry worker
- Periodinis jobas, kuris:
  - suranda expired `appointments.status=HELD` ir jas atstato i `CANCELLED` su `cancel_reason=HOLD_EXPIRED`;
  - istrina/isvaldo expired `conversation_locks`;
  - yra idempotentiskas.

4. Notifikaciju outbox ir worker
- `notification_outbox` lentele + siuntimo worker'is (WhatsApp/SMS/Telegram) su retry/backoff.
- Privalomi ivykiai: reschedule patvirtinimas, rytojaus patvirtinimas, incidentai (kai bus).
- Audit ir idempotency, kad nebutu dubliu.

5. Admin UI: RESCHEDULE srautas (preview -> confirm)
- Kalendoriuje prideti:
  - pasirinkta diena + resursas,
  - preview lentele (CANCEL/CREATE),
  - confirm mygtuka,
  - greiti reason mygtukai (pagal specifikacija Phase 1.1).

6. Testai (minimumas is specifikacijos)
- Concurrency: du vienalaikiai HOLD i ta pati slota (vienas turi laimeti).
- RESCHEDULE: `row_version` konfliktas -> 409.
- Lock: `lock_level>=2` -> tik ADMIN.
- Hold: confirm po expiry -> 409 arba 410.
- Daily approve: fiksuoja audit ir padidina `row_version`.

## Uzdarymo kriterijai (Definition of done)

Modulis laikomas uzdarytu kai:

- Voice ir chat kanalai naudoja Hold API realiame sraute.
- Expiry worker veikia ir nepalieka uzstrigusiu `HELD`.
- Notifikacijos iseina per outbox (su retry) ir yra audituojamos.
- Admin UI turi pilna RESCHEDULE preview/confirm srauta.
- Praeina minimalus testu rinkinys is specifikacijos.

