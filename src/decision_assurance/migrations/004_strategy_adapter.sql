-- Optional reference adapter; initialize explicitly, after the existing decision repository.
CREATE TABLE IF NOT EXISTS strategy_records (
 tenant_id TEXT NOT NULL, artifact_id TEXT NOT NULL, decision_id TEXT NOT NULL,
 mode TEXT NOT NULL CHECK(mode IN ('draft','baseline','observation')),
 request_hash TEXT NOT NULL, record_json TEXT NOT NULL,
 PRIMARY KEY(tenant_id,artifact_id),
 FOREIGN KEY(tenant_id,decision_id) REFERENCES decisions(tenant_id,decision_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS strategy_events (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL,
 decision_id TEXT NOT NULL, event_id TEXT NOT NULL, event_json TEXT NOT NULL,
 UNIQUE(tenant_id,event_id),
 FOREIGN KEY(tenant_id,decision_id) REFERENCES decisions(tenant_id,decision_id) ON DELETE CASCADE
);
