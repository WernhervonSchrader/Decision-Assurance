CREATE TABLE IF NOT EXISTS research_jobs (
    tenant_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    research_run_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('QUEUED','RUNNING','RETRY_WAIT','COMPLETED','PARTIAL','FAILED','CANCELLED','DEAD_LETTER')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lease_token_hash TEXT,
    lease_expires_at TIMESTAMPTZ,
    last_error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, job_id),
    UNIQUE (tenant_id, research_run_id),
    FOREIGN KEY (tenant_id, research_run_id) REFERENCES research_runs (tenant_id, research_run_id)
);

CREATE INDEX IF NOT EXISTS research_jobs_claim
ON research_jobs (status, available_at, created_at);

CREATE TABLE IF NOT EXISTS research_job_events (
    tenant_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, job_id, event_id),
    UNIQUE (tenant_id, job_id, sequence),
    FOREIGN KEY (tenant_id, job_id) REFERENCES research_jobs (tenant_id, job_id)
);

CREATE TABLE IF NOT EXISTS tenant_runtime_limits (
    tenant_id TEXT NOT NULL,
    max_concurrent_jobs INTEGER NOT NULL DEFAULT 2 CHECK (max_concurrent_jobs > 0),
    max_requests INTEGER NOT NULL DEFAULT 25 CHECK (max_requests > 0),
    max_results INTEGER NOT NULL DEFAULT 100 CHECK (max_results > 0),
    max_extractions INTEGER NOT NULL DEFAULT 25 CHECK (max_extractions > 0),
    max_cost_units INTEGER NOT NULL DEFAULT 100 CHECK (max_cost_units > 0),
    evidence_retention_days INTEGER NOT NULL DEFAULT 30 CHECK (evidence_retention_days > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id)
);

ALTER TABLE research_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY research_jobs_tenant_isolation ON research_jobs USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE research_job_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_job_events FORCE ROW LEVEL SECURITY;
CREATE POLICY research_job_events_tenant_isolation ON research_job_events USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE tenant_runtime_limits ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_runtime_limits FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_runtime_limits_tenant_isolation ON tenant_runtime_limits USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), '')) WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));

GRANT SELECT, INSERT, UPDATE, DELETE ON research_jobs, research_job_events, tenant_runtime_limits TO decision_assurance_application;
GRANT SELECT ON research_jobs, research_job_events, tenant_runtime_limits TO decision_assurance_operations_readonly;
GRANT SELECT ON research_job_events TO decision_assurance_audit_export;
