CREATE TABLE IF NOT EXISTS tenant_retention_policies (
    tenant_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    retention_days INTEGER NOT NULL CHECK (retention_days BETWEEN 1 AND 3650),
    backup_retention_days INTEGER NOT NULL CHECK (backup_retention_days BETWEEN 1 AND 3650),
    policy_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id)
);

CREATE TABLE IF NOT EXISTS legal_holds (
    tenant_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    hold_id TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    reason_code TEXT NOT NULL,
    created_by_actor_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    released_by_actor_hash TEXT,
    released_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, decision_id, hold_id),
    FOREIGN KEY (tenant_id, decision_id) REFERENCES decisions (tenant_id, decision_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_legal_hold_per_case
ON legal_holds (tenant_id, decision_id) WHERE active;

CREATE TABLE IF NOT EXISTS deletion_requests (
    tenant_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    decision_id TEXT,
    case_ref_hash TEXT NOT NULL,
    actor_hash TEXT NOT NULL,
    idempotency_key_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('REQUESTED','BLOCKED_BY_HOLD','EXECUTING','COMPLETED','FAILED')),
    reason_code TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, request_id),
    UNIQUE (tenant_id, actor_hash, idempotency_key_hash)
);

CREATE TABLE IF NOT EXISTS lifecycle_audit_events (
    tenant_id TEXT NOT NULL,
    sequence BIGINT GENERATED ALWAYS AS IDENTITY,
    event_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    case_ref_hash TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_json JSONB NOT NULL,
    event_hash TEXT NOT NULL,
    previous_event_hash TEXT,
    occurred_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, sequence),
    UNIQUE (tenant_id, event_id),
    FOREIGN KEY (tenant_id, request_id) REFERENCES deletion_requests (tenant_id, request_id)
);

ALTER TABLE tenant_retention_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_retention_policies FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_retention_policies_tenant_isolation ON tenant_retention_policies USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE legal_holds ENABLE ROW LEVEL SECURITY;
ALTER TABLE legal_holds FORCE ROW LEVEL SECURITY;
CREATE POLICY legal_holds_tenant_isolation ON legal_holds USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE deletion_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE deletion_requests FORCE ROW LEVEL SECURITY;
CREATE POLICY deletion_requests_tenant_isolation ON deletion_requests USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE lifecycle_audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE lifecycle_audit_events FORCE ROW LEVEL SECURITY;
CREATE POLICY lifecycle_audit_events_tenant_isolation ON lifecycle_audit_events USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));

GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_retention_policies, legal_holds, deletion_requests, lifecycle_audit_events TO decision_assurance_application;
GRANT USAGE, SELECT ON SEQUENCE lifecycle_audit_events_sequence_seq TO decision_assurance_application;
GRANT SELECT ON tenant_retention_policies, legal_holds, deletion_requests, lifecycle_audit_events TO decision_assurance_operations_readonly;
GRANT SELECT ON legal_holds, deletion_requests, lifecycle_audit_events TO decision_assurance_audit_export;
