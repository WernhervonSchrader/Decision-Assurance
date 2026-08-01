from __future__ import annotations

import json
import os
import sys

import psycopg

TENANT_TABLES = (
    "decisions",
    "reports",
    "audit_events",
    "intake_records",
    "research_runs",
    "research_jobs",
    "research_job_events",
)


def verify(dsn: str) -> dict[str, object]:
    with psycopg.connect(dsn) as connection:
        version = connection.execute("SELECT max(version) FROM schema_migrations").fetchone()
        if version != ("002",):
            raise RuntimeError("DATABASE_SCHEMA_VERSION_MISMATCH")
        rls = connection.execute(
            """
            SELECT relname, relrowsecurity, relforcerowsecurity
            FROM pg_class
            WHERE relname = ANY(%s) AND relkind = 'r'
            """,
            (list(TENANT_TABLES),),
        ).fetchall()
        if len(rls) != len(TENANT_TABLES) or any(not row[1] or not row[2] for row in rls):
            raise RuntimeError("RLS_RESTORE_VERIFICATION_FAILED")
        unsafe_roles = connection.execute(
            """
            SELECT rolname FROM pg_roles
            WHERE rolname LIKE 'decision_assurance_%'
              AND rolname <> 'decision_assurance_migration'
              AND (rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole)
            """
        ).fetchall()
        if unsafe_roles:
            raise RuntimeError("DATABASE_ROLE_VERIFICATION_FAILED")
        audit_gap = connection.execute(
            """
            SELECT 1 FROM (
                SELECT tenant_id, decision_id, sequence,
                       lag(sequence) OVER (
                           PARTITION BY tenant_id, decision_id ORDER BY sequence
                       ) AS previous_sequence
                FROM audit_events
            ) AS ordered
            WHERE previous_sequence IS NOT NULL AND sequence <= previous_sequence
            LIMIT 1
            """
        ).fetchone()
        if audit_gap is not None:
            raise RuntimeError("AUDIT_SEQUENCE_GAP")
    return {
        "schema_version": "0.5.0",
        "database_schema_version": "003",
        "rls_tables_verified": len(TENANT_TABLES),
        "status": "PASS",
    }


def main() -> None:
    dsn = os.getenv("DA_RESTORE_DSN")
    if not dsn:
        raise RuntimeError("DA_RESTORE_DSN_REQUIRED")
    try:
        report = verify(dsn)
    except (psycopg.Error, RuntimeError) as error:
        print(json.dumps({"status": "BLOCK", "reason_code": str(error)}))
        sys.exit(1)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
