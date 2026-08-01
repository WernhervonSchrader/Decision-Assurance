from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from decision_assurance.recovery.evidence import RecoveryEvidence


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include timezone")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate measured pilot recovery evidence")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--environment", required=True)
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
    verification = json.loads(verification_bytes)
    required = (
        "audit_chains_valid",
        "exports_valid",
        "tenant_isolation_valid",
        "session_decryption_valid",
    )
    if verification.get("status") != "PASS" or any(
        verification.get(name) is not True for name in required
    ):
        raise ValueError("RECOVERY_VERIFICATION_REPORT_FAILED")
    report = RecoveryEvidence(
        schema_version="1.0.0",
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
