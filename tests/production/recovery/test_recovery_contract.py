import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.postgres.generate_recovery_evidence import load_verification_report

ROOT = Path(__file__).parents[3]


def _verification_report() -> dict[str, object]:
    return {
        "schema_version": "0.5.0",
        "commit_sha": "a" * 40,
        "environment": "github-actions-postgresql-16",
        "source_database": "decision_assurance",
        "restore_database": "decision_assurance_restore",
        "server_version_num": "160009",
        "verification_completed_at": datetime.now(timezone.utc).isoformat(),
        "database_schema_version": "004",
        "rls_tables_verified": 13,
        "session_store_verified": True,
        "drill_data_verified": True,
        "drill_counts": {
            "decisions": 2,
            "audit_events": 2,
            "research_runs": 2,
            "browser_sessions": 2,
        },
        "post_backup_data_absent": True,
        "audit_chains_valid": True,
        "exports_valid": True,
        "tenant_isolation_valid": True,
        "session_decryption_valid": True,
        "status": "PASS",
    }


def test_recovery_report_is_bound_to_full_drill_commit_and_environment() -> None:
    report = _verification_report()
    loaded = load_verification_report(
        json.dumps(report).encode(),
        expected_commit_sha="a" * 40,
        expected_environment="github-actions-postgresql-16",
    )
    assert loaded["restore_database"] == "decision_assurance_restore"

    with pytest.raises(ValueError, match="RECOVERY_VERIFICATION_REPORT_INVALID"):
        load_verification_report(
            json.dumps({"status": "PASS", "audit_chains_valid": True}).encode(),
            expected_commit_sha="a" * 40,
            expected_environment="github-actions-postgresql-16",
        )
    report["commit_sha"] = "b" * 40
    with pytest.raises(ValueError, match="RECOVERY_VERIFICATION_REPORT_FAILED"):
        load_verification_report(
            json.dumps(report).encode(),
            expected_commit_sha="a" * 40,
            expected_environment="github-actions-postgresql-16",
        )


def test_backup_and_restore_are_checksum_verified_and_fail_fast() -> None:
    backup = (ROOT / "scripts" / "postgres" / "backup.ps1").read_text(encoding="utf-8")
    restore = (ROOT / "scripts" / "postgres" / "restore.ps1").read_text(encoding="utf-8")
    verifier = (ROOT / "scripts" / "postgres" / "verify_restore.py").read_text(encoding="utf-8")

    assert "pg_dump" in backup
    assert "Get-FileHash" in backup
    assert "backup-manifest.json" in backup
    assert "pg_restore" in restore
    assert "--single-transaction" in restore
    assert "BACKUP_CHECKSUM_MISMATCH" in restore
    assert 'database_schema_version = "004"' in backup
    assert "--no-privileges" not in restore
    assert "DA_RECOVERY_EXPECT_DRILL_DATA" in verifier
    assert "RECOVERY_DRILL_POST_BACKUP_DATA_PRESENT" in verifier
    assert "decision_assurance_private.browser_sessions" in verifier
    assert "schema_migrations" in verifier
    assert "relforcerowsecurity" in verifier
    assert "AUDIT_HASH_CHAIN_INVALID" in verifier
