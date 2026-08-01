-- Group roles. Login roles are provisioned by the deployment platform and inherit
-- exactly one of these roles. Passwords and other credentials never live here.
DO $roles$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'decision_assurance_migration') THEN
        CREATE ROLE decision_assurance_migration NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'decision_assurance_application') THEN
        CREATE ROLE decision_assurance_application NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'decision_assurance_operations_readonly') THEN
        CREATE ROLE decision_assurance_operations_readonly NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'decision_assurance_audit_export') THEN
        CREATE ROLE decision_assurance_audit_export NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'decision_assurance_worker') THEN
        CREATE ROLE decision_assurance_worker NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'decision_assurance_session_owner') THEN
        CREATE ROLE decision_assurance_session_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
END
$roles$;

-- The migration identity may transfer SECURITY DEFINER session objects to the
-- non-login/NOBYPASSRLS owner, but application and worker identities may not.
GRANT decision_assurance_session_owner TO decision_assurance_migration;
