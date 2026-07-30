CREATE TABLE IF NOT EXISTS decisions (
    tenant_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    document_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, decision_id)
);

CREATE TABLE IF NOT EXISTS reports (
    tenant_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    report_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, decision_id),
    FOREIGN KEY (tenant_id, decision_id) REFERENCES decisions (tenant_id, decision_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    tenant_id TEXT NOT NULL,
    sequence BIGINT GENERATED ALWAYS AS IDENTITY,
    decision_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_json JSONB NOT NULL,
    PRIMARY KEY (tenant_id, sequence),
    UNIQUE (tenant_id, decision_id, event_id),
    FOREIGN KEY (tenant_id, decision_id) REFERENCES decisions (tenant_id, decision_id)
);

CREATE TABLE IF NOT EXISTS idempotency (
    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    response_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, actor_id, operation, idempotency_key)
);

CREATE TABLE IF NOT EXISTS intake_records (
    tenant_id TEXT NOT NULL,
    intake_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RECEIVED','EXTRACTED','NEEDS_CONFIRMATION','READY','COMPILED','REJECTED')),
    record_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, intake_id)
);

CREATE TABLE IF NOT EXISTS intake_facts (
    tenant_id TEXT NOT NULL,
    intake_id TEXT NOT NULL,
    fact_id TEXT NOT NULL,
    fact_json JSONB NOT NULL,
    PRIMARY KEY (tenant_id, intake_id, fact_id),
    FOREIGN KEY (tenant_id, intake_id) REFERENCES intake_records (tenant_id, intake_id)
);

CREATE TABLE IF NOT EXISTS intake_confirmations (
    tenant_id TEXT NOT NULL,
    intake_id TEXT NOT NULL,
    confirmation_id TEXT NOT NULL,
    fact_id TEXT NOT NULL,
    confirmation_json JSONB NOT NULL,
    PRIMARY KEY (tenant_id, intake_id, confirmation_id),
    FOREIGN KEY (tenant_id, intake_id, fact_id) REFERENCES intake_facts (tenant_id, intake_id, fact_id)
);

CREATE TABLE IF NOT EXISTS intake_audit_events (
    tenant_id TEXT NOT NULL,
    intake_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_json JSONB NOT NULL,
    PRIMARY KEY (tenant_id, intake_id, event_id),
    UNIQUE (tenant_id, intake_id, sequence),
    FOREIGN KEY (tenant_id, intake_id) REFERENCES intake_records (tenant_id, intake_id)
);

CREATE TABLE IF NOT EXISTS intake_idempotency (
    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_json JSONB NOT NULL,
    PRIMARY KEY (tenant_id, actor_id, operation, idempotency_key)
);

CREATE TABLE IF NOT EXISTS research_runs (
    tenant_id TEXT NOT NULL,
    research_run_id TEXT NOT NULL,
    decision_file_id TEXT NOT NULL,
    semantic_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('CREATED','SEARCHING','SOURCES_DISCOVERED','EXTRACTING','EVIDENCE_COMPILED','COMPLETED','PARTIALLY_COMPLETED','FAILED','CANCELLED')),
    run_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, research_run_id),
    UNIQUE (tenant_id, semantic_fingerprint)
);

CREATE TABLE IF NOT EXISTS research_source_candidates (
    tenant_id TEXT NOT NULL,
    research_run_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_json JSONB NOT NULL,
    PRIMARY KEY (tenant_id, research_run_id, source_id),
    FOREIGN KEY (tenant_id, research_run_id) REFERENCES research_runs (tenant_id, research_run_id)
);

CREATE TABLE IF NOT EXISTS research_source_snapshots (
    tenant_id TEXT NOT NULL,
    research_run_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    snapshot_json JSONB NOT NULL,
    PRIMARY KEY (tenant_id, research_run_id, snapshot_id),
    UNIQUE (tenant_id, research_run_id, content_hash),
    FOREIGN KEY (tenant_id, research_run_id, source_id) REFERENCES research_source_candidates (tenant_id, research_run_id, source_id)
);

CREATE INDEX IF NOT EXISTS research_snapshot_cache
ON research_source_snapshots (tenant_id, canonical_url, expires_at);

CREATE TABLE IF NOT EXISTS research_evidence_candidates (
    tenant_id TEXT NOT NULL,
    research_run_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    evidence_json JSONB NOT NULL,
    PRIMARY KEY (tenant_id, research_run_id, evidence_id),
    UNIQUE (tenant_id, research_run_id, content_hash),
    FOREIGN KEY (tenant_id, research_run_id, source_id) REFERENCES research_source_candidates (tenant_id, research_run_id, source_id),
    FOREIGN KEY (tenant_id, research_run_id, snapshot_id) REFERENCES research_source_snapshots (tenant_id, research_run_id, snapshot_id)
);

CREATE TABLE IF NOT EXISTS research_attempts (
    tenant_id TEXT NOT NULL,
    research_run_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    attempt_json JSONB NOT NULL,
    PRIMARY KEY (tenant_id, research_run_id, attempt_id),
    FOREIGN KEY (tenant_id, research_run_id) REFERENCES research_runs (tenant_id, research_run_id)
);

CREATE TABLE IF NOT EXISTS research_audit_events (
    tenant_id TEXT NOT NULL,
    research_run_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_json JSONB NOT NULL,
    PRIMARY KEY (tenant_id, research_run_id, event_id),
    UNIQUE (tenant_id, research_run_id, sequence),
    FOREIGN KEY (tenant_id, research_run_id) REFERENCES research_runs (tenant_id, research_run_id)
);

CREATE TABLE IF NOT EXISTS research_idempotency (
    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    response_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, actor_id, operation, idempotency_key)
);

CREATE TABLE IF NOT EXISTS research_budget_usage (
    tenant_id TEXT NOT NULL,
    research_run_id TEXT NOT NULL,
    used_units INTEGER NOT NULL DEFAULT 0 CHECK (used_units >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, research_run_id),
    FOREIGN KEY (tenant_id, research_run_id) REFERENCES research_runs (tenant_id, research_run_id)
);

CREATE TABLE IF NOT EXISTS research_handoffs (
    tenant_id TEXT NOT NULL,
    research_run_id TEXT NOT NULL,
    decision_file_id TEXT NOT NULL,
    handoff_id TEXT NOT NULL,
    result_document_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, research_run_id, decision_file_id, handoff_id),
    FOREIGN KEY (tenant_id, research_run_id) REFERENCES research_runs (tenant_id, research_run_id),
    FOREIGN KEY (tenant_id, decision_file_id) REFERENCES decisions (tenant_id, decision_id)
);

ALTER TABLE decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE decisions FORCE ROW LEVEL SECURITY;
CREATE POLICY decisions_tenant_isolation ON decisions USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports FORCE ROW LEVEL SECURITY;
CREATE POLICY reports_tenant_isolation ON reports USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;
CREATE POLICY audit_events_tenant_isolation ON audit_events USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE idempotency ENABLE ROW LEVEL SECURITY;
ALTER TABLE idempotency FORCE ROW LEVEL SECURITY;
CREATE POLICY idempotency_tenant_isolation ON idempotency USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE intake_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE intake_records FORCE ROW LEVEL SECURITY;
CREATE POLICY intake_records_tenant_isolation ON intake_records USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE intake_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE intake_facts FORCE ROW LEVEL SECURITY;
CREATE POLICY intake_facts_tenant_isolation ON intake_facts USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE intake_confirmations ENABLE ROW LEVEL SECURITY;
ALTER TABLE intake_confirmations FORCE ROW LEVEL SECURITY;
CREATE POLICY intake_confirmations_tenant_isolation ON intake_confirmations USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE intake_audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE intake_audit_events FORCE ROW LEVEL SECURITY;
CREATE POLICY intake_audit_events_tenant_isolation ON intake_audit_events USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE intake_idempotency ENABLE ROW LEVEL SECURITY;
ALTER TABLE intake_idempotency FORCE ROW LEVEL SECURITY;
CREATE POLICY intake_idempotency_tenant_isolation ON intake_idempotency USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE research_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_runs FORCE ROW LEVEL SECURITY;
CREATE POLICY research_runs_tenant_isolation ON research_runs USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE research_source_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_source_candidates FORCE ROW LEVEL SECURITY;
CREATE POLICY research_source_candidates_tenant_isolation ON research_source_candidates USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE research_source_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_source_snapshots FORCE ROW LEVEL SECURITY;
CREATE POLICY research_source_snapshots_tenant_isolation ON research_source_snapshots USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE research_evidence_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_evidence_candidates FORCE ROW LEVEL SECURITY;
CREATE POLICY research_evidence_candidates_tenant_isolation ON research_evidence_candidates USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE research_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_attempts FORCE ROW LEVEL SECURITY;
CREATE POLICY research_attempts_tenant_isolation ON research_attempts USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE research_audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_audit_events FORCE ROW LEVEL SECURITY;
CREATE POLICY research_audit_events_tenant_isolation ON research_audit_events USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE research_idempotency ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_idempotency FORCE ROW LEVEL SECURITY;
CREATE POLICY research_idempotency_tenant_isolation ON research_idempotency USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE research_budget_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_budget_usage FORCE ROW LEVEL SECURITY;
CREATE POLICY research_budget_usage_tenant_isolation ON research_budget_usage USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE research_handoffs ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_handoffs FORCE ROW LEVEL SECURITY;
CREATE POLICY research_handoffs_tenant_isolation ON research_handoffs USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));

GRANT SELECT, INSERT, UPDATE, DELETE ON decisions, reports, audit_events, idempotency,
    intake_records, intake_facts, intake_confirmations, intake_audit_events, intake_idempotency,
    research_runs, research_source_candidates, research_source_snapshots,
    research_evidence_candidates, research_attempts, research_audit_events,
    research_idempotency, research_budget_usage, research_handoffs
TO decision_assurance_application;
GRANT USAGE, SELECT ON SEQUENCE audit_events_sequence_seq TO decision_assurance_application;
GRANT SELECT ON decisions, reports, audit_events, idempotency, intake_records, intake_facts,
    intake_confirmations, intake_audit_events, intake_idempotency, research_runs,
    research_source_candidates, research_source_snapshots, research_evidence_candidates,
    research_attempts, research_audit_events, research_idempotency, research_budget_usage,
    research_handoffs
TO decision_assurance_operations_readonly;
GRANT SELECT ON decisions, reports, audit_events, intake_audit_events, research_audit_events, research_handoffs TO decision_assurance_audit_export;
