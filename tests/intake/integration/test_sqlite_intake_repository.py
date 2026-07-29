import sqlite3
from pathlib import Path

import pytest

from decision_assurance.intake.repository import SqliteIntakeRepository
from decision_assurance.tenancy import TenantContext


def tenant(value: str) -> TenantContext:
    return TenantContext(value)


def test_intake_records_are_tenant_isolated(tmp_path: Path) -> None:
    repository = SqliteIntakeRepository(tmp_path / "intake.db")
    repository.initialize()
    repository.put(tenant("a"), "I-1", "RECEIVED", {"intake_id": "I-1"})
    repository.put(tenant("b"), "I-1", "RECEIVED", {"intake_id": "I-1"})
    assert repository.get(tenant("a"), "I-1") == {"intake_id": "I-1"}
    assert repository.get(tenant("c"), "I-1") is None


def test_cross_tenant_fact_relationship_is_rejected_by_database(tmp_path: Path) -> None:
    repository = SqliteIntakeRepository(tmp_path / "intake.db")
    repository.initialize()
    repository.put(tenant("a"), "I-1", "RECEIVED", {"intake_id": "I-1"})
    with (
        sqlite3.connect(repository.database_path) as connection,
        pytest.raises(sqlite3.IntegrityError),
    ):
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO intake_facts (tenant_id,intake_id,fact_id,fact_json) VALUES (?,?,?,?)",
            ("b", "I-1", "F-1", "{}"),
        )


def test_repeated_put_is_idempotent_but_cannot_change_identity(tmp_path: Path) -> None:
    repository = SqliteIntakeRepository(tmp_path / "intake.db")
    repository.initialize()
    repository.put(tenant("a"), "I-1", "READY", {"intake_id": "I-1", "ready": True})
    repository.put(tenant("a"), "I-1", "READY", {"intake_id": "I-1", "ready": True})
    assert repository.get(tenant("a"), "I-1") == {"intake_id": "I-1", "ready": True}
