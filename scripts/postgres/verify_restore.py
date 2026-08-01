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
    "tenant_retention_policies",
    "legal_holds",
    "legal_hold_audit_events",
    "deletion_requests",
    "lifecycle_audit_events",
)

DRILL_PRE_BACKUP_DECISIONS = ("recovery-decision-1", "recovery-decision-2")
DRILL_POST_BACKUP_DECISION = "recovery-post-backup"


def verify(dsn: str) -> dict[str, object]:
    verify_drill_data = os.getenv("DA_RECOVERY_EXPECT_DRILL_DATA") == "true"
    with psycopg.connect(dsn) as connection:
        version = connection.execute("SELECT max(version) FROM schema_migrations").fetchone()
        if version != ("004",):
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
        session_table = connection.execute(
            "SELECT to_regclass('decision_assurance_private.browser_sessions')"
        ).fetchone()
        if session_table != ("decision_assurance_private.browser_sessions",):
            raise RuntimeError("SESSION_STORE_RESTORE_VERIFICATION_FAILED")
        drill_counts: dict[str, int] = {}
        if verify_drill_data:
            checks = {
                "decisions": (
                    "SELECT count(*) FROM decisions WHERE decision_id = ANY(%s)",
                    (list(DRILL_PRE_BACKUP_DECISIONS),),
                    len(DRILL_PRE_BACKUP_DECISIONS),
                ),
                "audit_events": (
                    "SELECT count(*) FROM audit_events WHERE decision_id = ANY(%s)",
                    (list(DRILL_PRE_BACKUP_DECISIONS),),
                    len(DRILL_PRE_BACKUP_DECISIONS),
                ),
                "research_runs": (
                    "SELECT count(*) FROM research_runs WHERE research_run_id LIKE 'recovery-run-%'",
                    (),
                    2,
                ),
                "browser_sessions": (
                    "SELECT count(*) FROM decision_assurance_private.browser_sessions "
                    "WHERE actor_id LIKE 'recovery-actor-%'",
                    (),
                    2,
                ),
            }
            for name, (query, parameters, minimum) in checks.items():
                cursor = (
                    connection.execute(query, parameters)
                    if parameters
                    else connection.execute(query)
                )
                row = cursor.fetchone()
                count = int(row[0]) if row else 0
                if count < minimum:
                    raise RuntimeError(f"RECOVERY_DRILL_{name.upper()}_MISSING")
                drill_counts[name] = count
            post_backup = connection.execute(
                "SELECT 1 FROM decisions WHERE decision_id = %s",
                (DRILL_POST_BACKUP_DECISION,),
            ).fetchone()
            if post_backup is not None:
                raise RuntimeError("RECOVERY_DRILL_POST_BACKUP_DATA_PRESENT")
    return {
        "schema_version": "0.5.0",
        "database_schema_version": "004",
        "rls_tables_verified": len(TENANT_TABLES),
        "session_store_verified": True,
        "drill_data_verified": verify_drill_data,
        "drill_counts": drill_counts,
        "post_backup_data_absent": verify_drill_data,
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
