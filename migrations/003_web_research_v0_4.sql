PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS research_runs (
    tenant_id TEXT NOT NULL,
    research_run_id TEXT NOT NULL,
    decision_file_id TEXT NOT NULL,
    semantic_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('CREATED','SEARCHING','SOURCES_DISCOVERED','EXTRACTING','EVIDENCE_COMPILED','COMPLETED','PARTIALLY_COMPLETED','FAILED','CANCELLED')),
    run_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, research_run_id),
    UNIQUE (tenant_id, semantic_fingerprint)
);

CREATE TABLE IF NOT EXISTS research_source_candidates (
    tenant_id TEXT NOT NULL,
    research_run_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_json TEXT NOT NULL,
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
    expires_at TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
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
    evidence_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, research_run_id, evidence_id),
    UNIQUE (tenant_id, research_run_id, content_hash),
    FOREIGN KEY (tenant_id, research_run_id, source_id) REFERENCES research_source_candidates (tenant_id, research_run_id, source_id),
    FOREIGN KEY (tenant_id, research_run_id, snapshot_id) REFERENCES research_source_snapshots (tenant_id, research_run_id, snapshot_id)
);

CREATE TABLE IF NOT EXISTS research_attempts (
    tenant_id TEXT NOT NULL,
    research_run_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    attempt_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, research_run_id, attempt_id),
    FOREIGN KEY (tenant_id, research_run_id) REFERENCES research_runs (tenant_id, research_run_id)
);

CREATE TABLE IF NOT EXISTS research_audit_events (
    tenant_id TEXT NOT NULL,
    research_run_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_json TEXT NOT NULL,
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
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, actor_id, operation, idempotency_key)
);

CREATE TABLE IF NOT EXISTS research_budget_usage (
    tenant_id TEXT NOT NULL,
    research_run_id TEXT NOT NULL,
    used_units INTEGER NOT NULL DEFAULT 0 CHECK (used_units >= 0),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, research_run_id),
    FOREIGN KEY (tenant_id, research_run_id) REFERENCES research_runs (tenant_id, research_run_id)
);

CREATE TABLE IF NOT EXISTS research_handoffs (
    tenant_id TEXT NOT NULL,
    research_run_id TEXT NOT NULL,
    decision_file_id TEXT NOT NULL,
    handoff_id TEXT NOT NULL,
    result_document_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, research_run_id, decision_file_id, handoff_id),
    FOREIGN KEY (tenant_id, research_run_id) REFERENCES research_runs (tenant_id, research_run_id),
    FOREIGN KEY (tenant_id, decision_file_id) REFERENCES decisions (tenant_id, decision_id)
);
