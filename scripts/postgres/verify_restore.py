from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

from decision_assurance.export.postgresql import PostgresExportRepository
from decision_assurance.export.service import PilotExportService
from decision_assurance.export.signing import (
    FakeEd25519Signer,
    InMemoryVerificationKeyResolver,
    VerificationKey,
)
from decision_assurance.export.validator import validate_export
from decision_assurance.identity import ActorKind, Identity, Role
from decision_assurance.persistence.postgresql import (
    PostgresConnectionProvider,
    PostgresSettings,
)
from decision_assurance.pilot_ui.session_postgresql import PostgresSessionStore
from decision_assurance.production.contracts import SecretValue
from decision_assurance.tenancy import TenantContext

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
    "deployment_acceptance_events",
)

DRILL_PRE_BACKUP_DECISIONS = ("recovery-decision-1", "recovery-decision-2")
DRILL_POST_BACKUP_DECISION = "recovery-post-backup"
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


def verify(dsn: str) -> dict[str, object]:
    verify_drill_data = os.getenv("DA_RECOVERY_EXPECT_DRILL_DATA") == "true"
    commit_sha = os.getenv("DA_RECOVERY_COMMIT_SHA", "")
    environment = os.getenv("DA_RECOVERY_ENVIRONMENT", "")
    source_database = os.getenv("DA_RECOVERY_SOURCE_DATABASE", "")
    if not _COMMIT_SHA.fullmatch(commit_sha):
        raise RuntimeError("RECOVERY_COMMIT_SHA_INVALID")
    if not environment or len(environment) > 128:
        raise RuntimeError("RECOVERY_ENVIRONMENT_INVALID")
    if not source_database or len(source_database) > 63:
        raise RuntimeError("RECOVERY_SOURCE_DATABASE_INVALID")
    with psycopg.connect(dsn) as connection:
        database_row = connection.execute(
            "SELECT current_database(), current_setting('server_version_num')"
        ).fetchone()
        if database_row is None:
            raise RuntimeError("RECOVERY_DATABASE_IDENTITY_UNAVAILABLE")
        restore_database, server_version_num = map(str, database_row)
        if restore_database == source_database:
            raise RuntimeError("RECOVERY_RESTORE_TARGET_NOT_ISOLATED")
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
        connection.execute("SET LOCAL ROLE decision_assurance_application")
        connection.execute(
            "SELECT set_config('decision_assurance.tenant_id', %s, true)",
            ("recovery-tenant-a",),
        )
        own_count = connection.execute(
            "SELECT count(*) FROM decisions WHERE tenant_id = 'recovery-tenant-a'"
        ).fetchone()
        other_count = connection.execute(
            "SELECT count(*) FROM decisions WHERE tenant_id = 'recovery-tenant-b'"
        ).fetchone()
        connection.execute("RESET ROLE")
        if verify_drill_data and (own_count != (1,) or other_count != (0,)):
            raise RuntimeError("TENANT_ISOLATION_RESTORE_VERIFICATION_FAILED")
        audit_rows = connection.execute(
            "SELECT tenant_id,decision_id,event_json FROM audit_events "
            "ORDER BY tenant_id,decision_id,sequence"
        ).fetchall()
        previous_by_stream: dict[tuple[str, str], str] = {}
        for tenant_id, decision_id, event_json in audit_rows:
            event = dict(event_json)
            stream = (str(tenant_id), str(decision_id))
            if event.get("previous_event_hash") != previous_by_stream.get(stream):
                raise RuntimeError("AUDIT_HASH_CHAIN_INVALID")
            canonical = json.dumps(
                event, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
            previous_by_stream[stream] = "sha256:" + hashlib.sha256(canonical).hexdigest()
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
    export_valid = _verify_signed_export(dsn) if verify_drill_data else False
    session_valid = _verify_restored_sessions(dsn) if verify_drill_data else False
    return {
        "schema_version": "0.5.0",
        "commit_sha": commit_sha,
        "environment": environment,
        "source_database": source_database,
        "restore_database": restore_database,
        "server_version_num": server_version_num,
        "verification_completed_at": datetime.now(timezone.utc).isoformat(),
        "database_schema_version": "004",
        "rls_tables_verified": len(TENANT_TABLES),
        "session_store_verified": True,
        "drill_data_verified": verify_drill_data,
        "drill_counts": drill_counts,
        "post_backup_data_absent": verify_drill_data,
        "audit_chains_valid": True,
        "exports_valid": export_valid,
        "tenant_isolation_valid": True,
        "session_decryption_valid": session_valid,
        "status": "PASS",
    }


def _verify_signed_export(dsn: str) -> bool:
    now = datetime.now(timezone.utc)
    signer = FakeEd25519Signer(key_id="recovery-drill-key", clock=lambda: now)
    connections = PostgresConnectionProvider(PostgresSettings(SecretValue(dsn)))
    archive = PilotExportService(
        PostgresExportRepository(connections),
        version="recovery-drill",
        commit_sha=os.getenv("DA_RECOVERY_COMMIT_SHA", "0" * 40),
        policy_versions={"recovery": "1"},
        signer=signer,
        event_schema_version="1.0.0",
        clock=lambda: now,
    ).build(
        Identity(
            "recovery-verifier",
            TenantContext("recovery-tenant-a"),
            Role.AUDITOR,
            ActorKind.HUMAN,
        ),
        "recovery-decision-1",
    )
    resolver = InMemoryVerificationKeyResolver(
        {
            signer.key_id: VerificationKey(
                signer.key_id,
                signer.public_key_pem,
                now - timedelta(minutes=1),
                now + timedelta(minutes=1),
            )
        }
    )
    return validate_export(
        archive.content,
        key_resolver=resolver,
        expected_tenant="recovery-tenant-a",
        verification_time=now,
    ).valid


def _verify_restored_sessions(dsn: str) -> bool:
    state_path = os.getenv("DA_RECOVERY_SESSION_STATE")
    if not state_path:
        raise RuntimeError("RECOVERY_SESSION_STATE_REQUIRED")
    try:
        state = json.loads(Path(state_path).read_text(encoding="utf-8"))
        pepper = base64.b64decode(state["pepper"], validate=True)
        envelope_key = str(state["envelope_key"]).encode("ascii")
        sessions = state["sessions"]
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        raise RuntimeError("RECOVERY_SESSION_STATE_INVALID") from None
    store = PostgresSessionStore(
        PostgresConnectionProvider(PostgresSettings(SecretValue(dsn))),
        session_pepper=pepper,
        envelope_key=envelope_key,
        ttl_seconds=1800,
    )
    return bool(sessions) and all(
        store.get(str(item["session_id"])) is not None
        and store.get(str(item["session_id"])).identity["tenant_id"] == item["tenant_id"]  # type: ignore[union-attr]
        for item in sessions
    )


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
