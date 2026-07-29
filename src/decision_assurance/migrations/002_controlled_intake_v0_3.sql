PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS intake_records (
    tenant_id TEXT NOT NULL,
    intake_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RECEIVED','EXTRACTED','NEEDS_CONFIRMATION','READY','COMPILED','REJECTED')),
    record_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, intake_id)
);

CREATE TABLE IF NOT EXISTS intake_facts (
    tenant_id TEXT NOT NULL,
    intake_id TEXT NOT NULL,
    fact_id TEXT NOT NULL,
    fact_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, intake_id, fact_id),
    FOREIGN KEY (tenant_id, intake_id) REFERENCES intake_records (tenant_id, intake_id)
);

CREATE TABLE IF NOT EXISTS intake_confirmations (
    tenant_id TEXT NOT NULL,
    intake_id TEXT NOT NULL,
    confirmation_id TEXT NOT NULL,
    fact_id TEXT NOT NULL,
    confirmation_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, intake_id, confirmation_id),
    FOREIGN KEY (tenant_id, intake_id, fact_id) REFERENCES intake_facts (tenant_id, intake_id, fact_id)
);

CREATE TABLE IF NOT EXISTS intake_audit_events (
    tenant_id TEXT NOT NULL,
    intake_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_json TEXT NOT NULL,
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
    response_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, actor_id, operation, idempotency_key)
);
