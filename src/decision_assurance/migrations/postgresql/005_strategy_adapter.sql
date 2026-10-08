-- Additive optional strategy storage. Existing Decision File contract stays 0.2.0.
CREATE TABLE IF NOT EXISTS strategy_records (
 tenant_id TEXT NOT NULL, artifact_id TEXT NOT NULL, decision_id TEXT NOT NULL,
 mode TEXT NOT NULL CHECK(mode IN ('draft','baseline','observation')),
 request_hash TEXT NOT NULL, record_json JSONB NOT NULL,
 PRIMARY KEY(tenant_id,artifact_id),
 FOREIGN KEY(tenant_id,decision_id) REFERENCES decisions(tenant_id,decision_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS strategy_events (
 sequence BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 tenant_id TEXT NOT NULL, decision_id TEXT NOT NULL,
 event_id TEXT NOT NULL, event_json JSONB NOT NULL,
 UNIQUE(tenant_id,event_id),
 FOREIGN KEY(tenant_id,decision_id) REFERENCES decisions(tenant_id,decision_id) ON DELETE CASCADE
);
ALTER TABLE strategy_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE strategy_records FORCE ROW LEVEL SECURITY;
CREATE POLICY strategy_records_tenant_isolation ON strategy_records
 USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''))
 WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
ALTER TABLE strategy_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE strategy_events FORCE ROW LEVEL SECURITY;
CREATE POLICY strategy_events_tenant_isolation ON strategy_events
 USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''))
 WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
-- Runtime has no UPDATE/DELETE capability; case deletion uses existing controlled FK cascade.
GRANT SELECT, INSERT ON strategy_records, strategy_events TO decision_assurance_application;
GRANT USAGE, SELECT ON SEQUENCE strategy_events_sequence_seq TO decision_assurance_application;
GRANT SELECT ON strategy_records, strategy_events TO decision_assurance_operations_readonly;
GRANT SELECT ON strategy_events TO decision_assurance_audit_export;
