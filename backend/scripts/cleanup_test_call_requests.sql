-- Išvalo testines „Nauja skambucio uzklausa“ iš inbox.
-- Paleisti Supabase SQL Editor arba: psql $DATABASE_URL -f backend/scripts/cleanup_test_call_requests.sql

-- Peržiūrėti kiek bus ištrinta (paleisti pirmiau):
-- SELECT count(*) FROM call_requests WHERE status = 'NEW';

DELETE FROM call_requests WHERE status = 'NEW';
