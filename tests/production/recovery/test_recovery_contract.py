from pathlib import Path

ROOT = Path(__file__).parents[3]


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
    assert "DA_RECOVERY_EXPECT_DRILL_DATA" in verifier
    assert "RECOVERY_DRILL_POST_BACKUP_DATA_PRESENT" in verifier
    assert "decision_assurance_private.browser_sessions" in verifier
    assert "schema_migrations" in verifier
    assert "relforcerowsecurity" in verifier
    assert "AUDIT_SEQUENCE_GAP" in verifier
