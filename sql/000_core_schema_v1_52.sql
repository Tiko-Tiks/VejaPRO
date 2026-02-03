-- VEJAPRO Core Schema
-- Version: 1.52
-- Status: LOCKED / INITIAL CORE SNAPSHOT (v1.52)

CREATE TABLE projects (
    id UUID PRIMARY KEY,
    status TEXT NOT NULL,
    client_info JSONB NOT NULL,
    area_m2 NUMERIC NULL,
    is_certified BOOLEAN NOT NULL DEFAULT false,
    marketing_consent BOOLEAN NOT NULL DEFAULT false,
    vision_analysis JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE evidences (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    category TEXT NOT NULL,
    show_on_web BOOLEAN NOT NULL DEFAULT false,
    location_tag TEXT NULL,
    is_featured BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY,
    action TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    old_value JSONB NULL,
    new_value JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE margins (
    id UUID PRIMARY KEY,
    service_type TEXT NOT NULL,
    margin_percent NUMERIC NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_projects_created_at ON projects (created_at);
CREATE INDEX idx_projects_is_certified ON projects (is_certified);
CREATE UNIQUE INDEX idx_margins_active ON margins (service_type) WHERE valid_until IS NULL;

