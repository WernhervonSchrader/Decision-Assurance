import sqlite3
from datetime import datetime, timezone

import pytest

from decision_assurance.intake.repository import SqliteIntakeRepository
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.tenancy import TenantContext
from decision_assurance.web_research.contracts import (
    FreshnessPolicy,
    ResearchRequest,
    ResearchRun,
    ResearchStatus,
)
from decision_assurance.web_research.repository import (
    ResearchIdempotencyConflict,
    SqliteResearchRepository,
)

NOW = datetime(2026, 7, 29, tzinfo=timezone.utc).isoformat()


def make_run(tenant_id: str, run_id: str = "run-1", fingerprint: str | None = None) -> ResearchRun:
    return ResearchRun(
        research_run_id=run_id,
        tenant_id=tenant_id,
        actor_id="actor-1",
        request=ResearchRequest(
            decision_file_id="D-1",
            claim_refs=("claim-1",),
            query="rules",
            locale="en-US",
            preferred_languages=("en",),
            freshness=FreshnessPolicy(),
        ),
        expected_document_hash="sha256:" + "a" * 64,
        semantic_fingerprint=fingerprint or "sha256:" + "b" * 64,
        status=ResearchStatus.CREATED,
        created_at=NOW,
        updated_at=NOW,
        correlation_id="correlation-1",
    )


def repository(tmp_path) -> SqliteResearchRepository:  # type: ignore[no-untyped-def]
    value = SqliteResearchRepository(tmp_path / "research.db")
    value.initialize()
    return value


def test_runs_and_semantic_idempotency_are_tenant_isolated(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo = repository(tmp_path)
    tenant_a, tenant_b = TenantContext("tenant-a"), TenantContext("tenant-b")
    run_a = repo.create_or_get(tenant_a, make_run("tenant-a"))
    run_b = repo.create_or_get(tenant_b, make_run("tenant-b"))

    assert run_a.tenant_id == "tenant-a"
    assert run_b.tenant_id == "tenant-b"
    assert repo.get(tenant_a, "run-1") is not None
    assert repo.get(TenantContext("tenant-c"), "run-1") is None

    duplicate = make_run("tenant-a", "run-2")
    assert repo.create_or_get(tenant_a, duplicate).research_run_id == "run-1"


def test_cross_tenant_child_relationship_is_rejected_by_database(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo = repository(tmp_path)
    repo.create_or_get(TenantContext("tenant-a"), make_run("tenant-a"))
    with repo._connect() as connection:  # noqa: SLF001 - proves database boundary
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO research_source_candidates "
                "(tenant_id,research_run_id,source_id,source_json) VALUES (?,?,?,?)",
                ("tenant-b", "run-1", "source-1", "{}"),
            )


def test_http_idempotency_replays_and_conflicts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo = repository(tmp_path)
    tenant = TenantContext("tenant-a")
    repo.store_idempotency(tenant, "actor", "research:create", "key", "hash-1", 201, {"id": 1})
    assert repo.get_idempotency(tenant, "actor", "research:create", "key", "hash-1") == (
        201,
        {"id": 1},
    )
    with pytest.raises(ResearchIdempotencyConflict, match="IDEMPOTENCY_KEY_REUSED"):
        repo.get_idempotency(tenant, "actor", "research:create", "key", "hash-2")


def test_budget_reservation_is_atomic_and_bounded(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo = repository(tmp_path)
    tenant = TenantContext("tenant-a")
    repo.create_or_get(tenant, make_run("tenant-a"))
    assert repo.reserve_budget(tenant, "run-1", limit=2) == 1
    assert repo.reserve_budget(tenant, "run-1", limit=2) == 2
    with pytest.raises(ValueError, match="BUDGET_EXCEEDED"):
        repo.reserve_budget(tenant, "run-1", limit=2)


def test_migration_upgrades_existing_v03_database_without_losing_data(tmp_path) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "upgrade.db"
    decisions = SqliteDecisionRepository(database)
    intakes = SqliteIntakeRepository(database)
    decisions.initialize()
    intakes.initialize()
    tenant = TenantContext("tenant-a")
    with decisions._connect() as connection:  # noqa: SLF001 - migration verification
        connection.execute(
            "INSERT INTO decisions (tenant_id,decision_id,document_json) VALUES (?,?,?)",
            (tenant.tenant_id, "D-existing", "{}"),
        )

    research = SqliteResearchRepository(database)
    research.initialize()

    with decisions._connect() as connection:  # noqa: SLF001 - migration verification
        assert connection.execute(
            "SELECT 1 FROM decisions WHERE tenant_id=? AND decision_id=?",
            (tenant.tenant_id, "D-existing"),
        ).fetchone()
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_runs'"
        ).fetchone()
