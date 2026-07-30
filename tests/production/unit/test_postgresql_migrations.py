from pathlib import Path

import pytest

from decision_assurance.persistence.postgresql import (
    MigrationIntegrityError,
    discover_migrations,
    migration_checksum,
)


def test_discovers_ordered_contiguous_versioned_migrations(tmp_path: Path) -> None:
    (tmp_path / "002_second.sql").write_text("SELECT 2;", encoding="utf-8")
    (tmp_path / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "roles.sql").write_text("SELECT 0;", encoding="utf-8")

    migrations = discover_migrations(tmp_path)

    assert [item.version for item in migrations] == ["001", "002"]
    assert [item.name for item in migrations] == ["001_first.sql", "002_second.sql"]


def test_rejects_a_gap_in_the_migration_sequence(tmp_path: Path) -> None:
    (tmp_path / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "003_third.sql").write_text("SELECT 3;", encoding="utf-8")

    with pytest.raises(MigrationIntegrityError, match="MIGRATION_SEQUENCE_GAP"):
        discover_migrations(tmp_path)


def test_checksum_is_stable_and_content_sensitive(tmp_path: Path) -> None:
    migration = tmp_path / "001_first.sql"
    migration.write_bytes(b"SELECT 1;\n")
    first = migration_checksum(migration)

    assert first == migration_checksum(migration)
    migration.write_bytes(b"SELECT 2;\n")
    assert first != migration_checksum(migration)
