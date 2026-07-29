PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS decisions (
    tenant_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    document_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, decision_id)
);

CREATE TABLE IF NOT EXISTS reports (
    tenant_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, decision_id),
    FOREIGN KEY (tenant_id, decision_id) REFERENCES decisions (tenant_id, decision_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_json TEXT NOT NULL,
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
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, actor_id, operation, idempotency_key)
);

