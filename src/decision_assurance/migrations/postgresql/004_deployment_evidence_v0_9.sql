CREATE SCHEMA IF NOT EXISTS decision_assurance_private;
REVOKE ALL ON SCHEMA decision_assurance_private FROM PUBLIC;

CREATE TABLE IF NOT EXISTS deployment_acceptance_events (
    tenant_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    event_json JSONB NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
);
ALTER TABLE deployment_acceptance_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE deployment_acceptance_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS deployment_acceptance_events_tenant_isolation
ON deployment_acceptance_events;
CREATE POLICY deployment_acceptance_events_tenant_isolation
ON deployment_acceptance_events
USING (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''))
WITH CHECK (tenant_id = NULLIF(current_setting('decision_assurance.tenant_id', true), ''));
REVOKE ALL ON deployment_acceptance_events FROM PUBLIC;
REVOKE UPDATE, DELETE, TRUNCATE ON deployment_acceptance_events
FROM decision_assurance_application;
GRANT SELECT, INSERT ON deployment_acceptance_events TO decision_assurance_application;
GRANT SELECT ON deployment_acceptance_events
TO decision_assurance_operations_readonly, decision_assurance_audit_export;

CREATE TABLE IF NOT EXISTS decision_assurance_private.browser_sessions (
    session_digest TEXT PRIMARY KEY CHECK (session_digest ~ '^sha256:[0-9a-f]{64}$'),
    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    identity_json JSONB NOT NULL,
    csrf_token TEXT NOT NULL,
    token_ciphertext TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS browser_sessions_actor_idx
ON decision_assurance_private.browser_sessions (tenant_id, actor_id);
ALTER TABLE decision_assurance_private.browser_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_assurance_private.browser_sessions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS browser_sessions_tenant_isolation
ON decision_assurance_private.browser_sessions;
CREATE POLICY browser_sessions_tenant_isolation
ON decision_assurance_private.browser_sessions
USING (
    tenant_id = current_setting('decision_assurance.tenant_id', true)
    OR session_digest = current_setting('decision_assurance.session_digest', true)
)
WITH CHECK (
    tenant_id = current_setting('decision_assurance.tenant_id', true)
    OR session_digest = current_setting('decision_assurance.session_digest', true)
);
REVOKE ALL ON decision_assurance_private.browser_sessions FROM PUBLIC;
REVOKE ALL ON decision_assurance_private.browser_sessions FROM decision_assurance_application;

CREATE OR REPLACE FUNCTION da_create_browser_session(
    p_digest TEXT, p_tenant TEXT, p_actor TEXT, p_identity JSONB,
    p_csrf TEXT, p_token TEXT, p_expires TIMESTAMPTZ
) RETURNS VOID
LANGUAGE SQL SECURITY DEFINER
SET search_path = pg_catalog, public, decision_assurance_private
AS $$
    INSERT INTO decision_assurance_private.browser_sessions
        (session_digest, tenant_id, actor_id, identity_json, csrf_token, token_ciphertext, expires_at)
    SELECT p_digest, p_tenant, p_actor, p_identity, p_csrf, p_token, p_expires
    WHERE p_tenant = current_setting('decision_assurance.tenant_id', true);
$$;

CREATE OR REPLACE FUNCTION da_get_browser_session(p_digest TEXT)
RETURNS TABLE (identity_json JSONB, csrf_token TEXT, token_ciphertext TEXT, expires_at TIMESTAMPTZ)
LANGUAGE SQL SECURITY DEFINER
SET search_path = pg_catalog, public, decision_assurance_private
AS $$
    SELECT s.identity_json, s.csrf_token, s.token_ciphertext, s.expires_at
    FROM decision_assurance_private.browser_sessions s
    WHERE s.session_digest = p_digest AND s.revoked_at IS NULL AND s.expires_at > CURRENT_TIMESTAMP;
$$;

CREATE OR REPLACE FUNCTION da_revoke_browser_session(p_digest TEXT)
RETURNS VOID
LANGUAGE SQL SECURITY DEFINER
SET search_path = pg_catalog, public, decision_assurance_private
AS $$
    UPDATE decision_assurance_private.browser_sessions
    SET revoked_at = CURRENT_TIMESTAMP
    WHERE session_digest = p_digest AND revoked_at IS NULL;
$$;

CREATE OR REPLACE FUNCTION da_revoke_actor_sessions(p_tenant TEXT, p_actor TEXT)
RETURNS VOID
LANGUAGE SQL SECURITY DEFINER
SET search_path = pg_catalog, public, decision_assurance_private
AS $$
    UPDATE decision_assurance_private.browser_sessions
    SET revoked_at = CURRENT_TIMESTAMP
    WHERE tenant_id = p_tenant AND actor_id = p_actor AND revoked_at IS NULL
      AND p_tenant = current_setting('decision_assurance.tenant_id', true);
$$;

REVOKE ALL ON FUNCTION da_create_browser_session(TEXT,TEXT,TEXT,JSONB,TEXT,TEXT,TIMESTAMPTZ) FROM PUBLIC;
REVOKE ALL ON FUNCTION da_get_browser_session(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION da_revoke_browser_session(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION da_revoke_actor_sessions(TEXT,TEXT) FROM PUBLIC;
ALTER TABLE decision_assurance_private.browser_sessions OWNER TO decision_assurance_session_owner;
ALTER FUNCTION da_create_browser_session(TEXT,TEXT,TEXT,JSONB,TEXT,TEXT,TIMESTAMPTZ) OWNER TO decision_assurance_session_owner;
ALTER FUNCTION da_get_browser_session(TEXT) OWNER TO decision_assurance_session_owner;
ALTER FUNCTION da_revoke_browser_session(TEXT) OWNER TO decision_assurance_session_owner;
ALTER FUNCTION da_revoke_actor_sessions(TEXT,TEXT) OWNER TO decision_assurance_session_owner;
GRANT USAGE ON SCHEMA decision_assurance_private TO decision_assurance_session_owner;
GRANT EXECUTE ON FUNCTION da_create_browser_session(TEXT,TEXT,TEXT,JSONB,TEXT,TEXT,TIMESTAMPTZ) TO decision_assurance_application;
GRANT EXECUTE ON FUNCTION da_get_browser_session(TEXT) TO decision_assurance_application;
GRANT EXECUTE ON FUNCTION da_revoke_browser_session(TEXT) TO decision_assurance_application;
GRANT EXECUTE ON FUNCTION da_revoke_actor_sessions(TEXT,TEXT) TO decision_assurance_application;
