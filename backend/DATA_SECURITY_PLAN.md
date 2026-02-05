# Data Security And Retention Plan

## Scope
This document describes how we handle PII, audit logs, and retention for the
VejaPRO backend. It is a practical checklist for production operations.

## Data Classes
- PII: phone numbers, email addresses, physical address fields.
- Operational metadata: IP address, user agent, actor IDs.
- Payments: Stripe event metadata, payment status.
- Evidence: file URLs and metadata.

## Storage Locations
- Postgres (Supabase): `projects`, `audit_logs`, `payments`, `sms_confirmations`,
  `evidences`, `users`.
- Logs: nginx access/error, systemd journal.

## PII Redaction (Audit Logs)
We support optional PII redaction for `audit_logs.old_value`, `audit_logs.new_value`
and `audit_logs.metadata`.

Settings (env):
- `PII_REDACTION_ENABLED=true|false`
- `PII_REDACTION_FIELDS=phone,email,address,ssn,tax_id,passport,national_id,id_number`

Defaults:
- Enabled by default.
- Fields list above.

## Retention Policy
- `audit_logs`: keep for 90 days by default.
- System logs: 7 days (journald), nginx rotates daily and keeps 14 files.

Setting (env):
- `AUDIT_LOG_RETENTION_DAYS=90`

## Manual Purge (SQL)
Run in Supabase SQL editor or `psql`:
```sql
DELETE FROM audit_logs
WHERE timestamp < now() - (interval '1 day' * 90);
```

If you set a different value, replace `90` with the value of
`AUDIT_LOG_RETENTION_DAYS`.

## Operational Checklist
1. Confirm `PII_REDACTION_ENABLED=true` in production.
2. Confirm `AUDIT_LOG_RETENTION_DAYS` value.
3. Schedule periodic purge (manual or via a cron job calling the SQL above).
4. Document any changes to the retention policy.
