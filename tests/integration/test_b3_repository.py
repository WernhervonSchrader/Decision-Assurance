"""The same snapshot/rollback properties run on SQLite and opt-in PostgreSQL."""

from __future__ import annotations

import copy
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import psycopg
import pytest
from psycopg import sql

from decision_assurance.decision_file import DecisionFileSemanticError
from decision_assurance.persistence.postgresql import (
    PostgresConnectionProvider,
    PostgresMigrationRunner,
    PostgresSettings,
)
from decision_assurance.production.contracts import SecretValue
from decision_assurance.repositories.postgresql import PostgresDecisionRepository
from decision_assurance.repositories.protocols import DecisionWriteConflict
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.tenancy import TenantContext

ROOT = Path(__file__).parents[2]
TENANT = TenantContext("b3-repository-a")
OTHER = TenantContext("b3-repository-b")


@pytest.fixture(params=["sqlite", pytest.param("postgresql", marks=pytest.mark.postgresql)])
def repository(request, tmp_path):  # type: ignore[no-untyped-def]
    if request.param == "sqlite":
        result = SqliteDecisionRepository(tmp_path / "b3.db")
        result.initialize()
        yield result
    else:
        dsn = os.getenv("DA_TEST_POSTGRES_DSN")
        if not dsn:
            if os.getenv("CI"):
                pytest.fail("DA_TEST_POSTGRES_DSN_REQUIRED_IN_CI")
            pytest.skip("PostgreSQL requires DA_TEST_POSTGRES_DSN")
        migrations = ROOT / "migrations/postgresql"
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute((migrations / "roles.sql").read_text())
        settings = PostgresSettings(SecretValue(dsn))
        PostgresMigrationRunner(settings, migrations).migrate()

        def clear():  # type: ignore[no-untyped-def]
            with psycopg.connect(dsn, autocommit=True) as connection:
                for table in ("reports", "audit_events", "idempotency", "decisions"):
                    connection.execute(
                        sql.SQL("DELETE FROM {} WHERE tenant_id = ANY(%s)").format(
                            sql.Identifier(table)
                        ),
                        ([TENANT.tenant_id, OTHER.tenant_id],),
                    )

        clear()
        yield PostgresDecisionRepository(PostgresConnectionProvider(settings))
        clear()


def example():  # type: ignore[no-untyped-def]
    return json.loads((ROOT / "examples/decision-cases/low-risk-pass.json").read_text())


@pytest.mark.parametrize("status", ["VALIDATION", "REVIEW", "APPROVED", "BLOCKED"])
def test_repository_creation_cannot_import_lifecycle(repository, status):  # type: ignore[no-untyped-def]
    document = example()
    document["status"] = status
    with pytest.raises(DecisionFileSemanticError, match="INITIAL_LIFECYCLE_AUTHORITY_FORBIDDEN"):
        repository.create_decision(TENANT, document)
    assert repository.get_decision(TENANT, document["decision_id"]) is None


def test_creation_cannot_import_approval_even_when_draft(repository):  # type: ignore[no-untyped-def]
    document = example()
    document["approvals"] = [{"fake": "approval"}]
    with pytest.raises(DecisionFileSemanticError):
        repository.create_decision(TENANT, document)
    assert repository.get_decision(TENANT, document["decision_id"]) is None


def test_stale_write_rolls_back_report_audit_and_idempotency(repository):  # type: ignore[no-untyped-def]
    original = example()
    repository.create_decision(TENANT, original)
    winner = copy.deepcopy(original)
    winner["title"] = "Newer authorized snapshot"
    report = {"outcome": "REVIEW"}
    event = {"event_id": "winner", "event_type": "decision.evaluated"}
    repository.save_result(TENANT, winner, report, [event], expected_document=original)
    loser = copy.deepcopy(original)
    loser["status"] = "APPROVED"
    with pytest.raises(DecisionWriteConflict):
        repository.save_result(
            TENANT,
            loser,
            {"outcome": "PASS"},
            [{"event_id": "loser"}],
            ("actor", "approve", "key", "digest", 200, loser),
            expected_document=original,
        )
    assert repository.get_decision(TENANT, original["decision_id"]) == winner
    assert repository.get_report(TENANT, original["decision_id"]) == report
    assert repository.list_audit(TENANT, original["decision_id"], limit=100, offset=0) == [event]
    assert repository.get_idempotency(TENANT, "actor", "approve", "key", "digest") is None


def test_snapshot_comparison_is_tenant_scoped(repository):  # type: ignore[no-untyped-def]
    first = example()
    second = {**first, "title": "Other tenant content"}
    repository.create_decision(TENANT, first)
    repository.create_decision(OTHER, second)
    with pytest.raises(DecisionWriteConflict):
        repository.save_result(
            OTHER, {**second, "status": "APPROVED"}, None, [], expected_document=first
        )
    assert repository.get_decision(TENANT, first["decision_id"]) == first
    assert repository.get_decision(OTHER, first["decision_id"]) == second


def test_two_competing_snapshots_commit_once(repository):  # type: ignore[no-untyped-def]
    original = example()
    repository.create_decision(TENANT, original)
    barrier = Barrier(2)

    def write(title):  # type: ignore[no-untyped-def]
        updated = {**original, "title": title}
        barrier.wait(timeout=10)
        try:
            repository.save_result(TENANT, updated, None, [], expected_document=original)
        except DecisionWriteConflict:
            return "CONFLICT"
        return "SAVED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, ["one", "two"])) == ["CONFLICT", "SAVED"]
    assert repository.get_decision(TENANT, original["decision_id"])["title"] in {"one", "two"}


def test_failed_audit_insert_rolls_back_entire_write(repository):  # type: ignore[no-untyped-def]
    original = example()
    event = {"event_id": "duplicate", "event_type": "test.fixture"}
    repository.create_decision(TENANT, original, [event])
    with pytest.raises((sqlite3.IntegrityError, psycopg.IntegrityError)):
        repository.save_result(
            TENANT,
            {**original, "status": "APPROVED"},
            {"outcome": "PASS"},
            [event],
            ("actor", "approve", "key", "digest", 200, original),
            expected_document=original,
        )
    assert repository.get_decision(TENANT, original["decision_id"]) == original
    assert repository.get_report(TENANT, original["decision_id"]) is None
    assert repository.list_audit(TENANT, original["decision_id"], limit=100, offset=0) == [event]
    assert repository.get_idempotency(TENANT, "actor", "approve", "key", "digest") is None
