from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from decision_assurance.recovery.evidence import RecoveryEvidence

_EXPECTED_VERIFICATION_FIELDS = frozenset(
    {
        "schema_version",
        "commit_sha",
        "environment",
        "source_database",
        "restore_database",
        "server_version_num",
        "verification_completed_at",
        "database_schema_version",
        "rls_tables_verified",
        "session_store_verified",
        "drill_data_verified",
        "drill_counts",
        "post_backup_data_absent",
        "audit_chains_valid",
        "exports_valid",
        "tenant_isolation_valid",
        "session_decryption_valid",
        "status",
    }
)
_BOOLEAN_CHECKS = (
    "session_store_verified",
    "drill_data_verified",
    "post_backup_data_absent",
    "audit_chains_valid",
    "exports_valid",
    "tenant_isolation_valid",
    "session_decryption_valid",
)
_MINIMUM_DRILL_COUNTS = {
    "decisions": 2,
    "audit_events": 2,
    "research_runs": 2,
    "browser_sessions": 2,
}
_DATABASE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]{0,62}$")
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_POSTGRESQL_16_VERSION = re.compile(r"^16[0-9]{4}$")


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include timezone")
    return parsed


def load_verification_report(
    content: bytes, *, expected_commit_sha: str, expected_environment: str
) -> dict[str, Any]:
    try:
        verification = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("RECOVERY_VERIFICATION_REPORT_INVALID") from None
    if not isinstance(verification, dict) or set(verification) != _EXPECTED_VERIFICATION_FIELDS:
        raise ValueError("RECOVERY_VERIFICATION_REPORT_INVALID")
    counts: Any = verification.get("drill_counts")
    valid_counts = isinstance(counts, dict) and set(counts) == set(_MINIMUM_DRILL_COUNTS)
    if valid_counts:
        valid_counts = all(
            isinstance(counts[name], int)
            and not isinstance(counts[name], bool)
            and counts[name] >= minimum
            for name, minimum in _MINIMUM_DRILL_COUNTS.items()
        )
    try:
        completed = _instant(str(verification["verification_completed_at"]))
    except (argparse.ArgumentTypeError, ValueError):
        raise ValueError("RECOVERY_VERIFICATION_REPORT_FAILED") from None
    if (
        verification.get("status") != "PASS"
        or verification.get("schema_version") != "0.5.0"
        or not _COMMIT_SHA.fullmatch(expected_commit_sha)
        or verification.get("commit_sha") != expected_commit_sha
        or not isinstance(expected_environment, str)
        or not 1 <= len(expected_environment) <= 128
        or verification.get("environment") != expected_environment
        or verification.get("database_schema_version") != "004"
        or verification.get("rls_tables_verified") != 28
        or not isinstance(verification.get("server_version_num"), str)
        or not _POSTGRESQL_16_VERSION.fullmatch(verification["server_version_num"])
        or not isinstance(verification.get("source_database"), str)
        or not _DATABASE_NAME.fullmatch(verification["source_database"])
        or not isinstance(verification.get("restore_database"), str)
        or not _DATABASE_NAME.fullmatch(verification["restore_database"])
        or verification["source_database"] == verification["restore_database"]
        or any(verification.get(name) is not True for name in _BOOLEAN_CHECKS)
        or not valid_counts
        or completed > datetime.now(completed.tzinfo)
    ):
        raise ValueError("RECOVERY_VERIFICATION_REPORT_FAILED")
    return verification


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate measured pilot recovery evidence")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--data-bytes", required=True, type=int)
    parser.add_argument("--backup-started", required=True, type=_instant)
    parser.add_argument("--backup-completed", required=True, type=_instant)
    parser.add_argument("--failure-at", required=True, type=_instant)
    parser.add_argument("--restore-started", required=True, type=_instant)
    parser.add_argument("--restore-completed", required=True, type=_instant)
    parser.add_argument("--latest-restored-record-at", required=True, type=_instant)
    parser.add_argument("--verification-report", required=True, type=Path)
    parser.add_argument("--target-rpo-seconds", type=int, default=300)
    parser.add_argument("--target-rto-seconds", type=int, default=900)
    arguments = parser.parse_args()
    verification_bytes = arguments.verification_report.read_bytes()
    verification = load_verification_report(
        verification_bytes,
        expected_commit_sha=arguments.commit_sha,
        expected_environment=arguments.environment,
    )
    report = RecoveryEvidence(
        schema_version="1.0.0",
        deployment_id=arguments.deployment_id,
        environment=arguments.environment,
        commit_sha=arguments.commit_sha,
        data_bytes=arguments.data_bytes,
        backup_started=arguments.backup_started,
        backup_completed=arguments.backup_completed,
        failure_at=arguments.failure_at,
        restore_started=arguments.restore_started,
        restore_completed=arguments.restore_completed,
        latest_restored_record_at=arguments.latest_restored_record_at,
        audit_chains_valid=verification["audit_chains_valid"],
        exports_valid=verification["exports_valid"],
        tenant_isolation_valid=verification["tenant_isolation_valid"],
        session_decryption_valid=verification["session_decryption_valid"],
        verification_report_sha256="sha256:" + hashlib.sha256(verification_bytes).hexdigest(),
        target_rpo_seconds=arguments.target_rpo_seconds,
        target_rto_seconds=arguments.target_rto_seconds,
    ).report()
    arguments.output.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
