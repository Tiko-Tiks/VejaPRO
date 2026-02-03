# SQL Core Audit v1.52
Status: LOCKED / Audit Snapshot (v1.52)

## CORE
- projects.id — Primary identifier for project lifecycle.
- projects.status — Status machine backbone (DRAFT→...→ACTIVE).
- projects.client_info — Canonical client payload (must exist).
- projects.created_at — Audit trail for creation timing.
- projects.updated_at — Canonical change timestamp.
- evidences.id — Primary identifier for evidence.
- evidences.project_id — Project linkage (FK deferred by design).
- evidences.category — Evidence classification (SITE_BEFORE / EXPERT_CERTIFICATION / etc.).
- evidences.created_at — Evidence timestamp.
- audit_logs.id — Primary identifier for audit entry.
- audit_logs.action — Canonical action code.
- audit_logs.actor_role — Actor role for audit accountability.
- audit_logs.entity_type — Entity type for audit.
- audit_logs.entity_id — Entity id for audit.
- audit_logs.created_at — Audit timestamp.
- margins.id — Primary identifier for margin rule.
- margins.service_type — Service key for pricing logic.
- margins.margin_percent — Margin value.
- margins.valid_from — Effective start.
- margins.valid_until — Effective end (null = active).
- margins.created_at — Rule creation timestamp.

## OPTIONAL
- projects.area_m2 — Optional estimated area (not required for core flow).
- projects.is_certified — Derived flag (status-based, but stored).
- projects.marketing_consent — Optional consent flag.
- projects.vision_analysis — Optional AI metadata payload.
- evidences.show_on_web — Optional marketing flag.
- evidences.location_tag — Optional geo tag for gallery.
- evidences.is_featured — Optional marketing flag.
- audit_logs.old_value — Optional previous state snapshot.
- audit_logs.new_value — Optional next state snapshot.

## DEFERRED
- Foreign keys (projects↔evidences, etc.) — Deferred to later iteration.
- CHECK constraints for status transitions — Enforced at app/service layer for now.
- ENUM types for statuses/categories — Deferred; using TEXT per v1.52 rule.
- Additional indexes beyond core (performance tuning) — Planned for later iteration.

