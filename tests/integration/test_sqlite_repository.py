import json
from pathlib import Path

import pytest

from decision_assurance.repositories.sqlite import (
    IdempotencyConflict,
    SqliteDecisionRepository,
)
from decision_assurance.tenancy import TenantContext


ROOT = Path(__file__).parents[2]


def example() -> dict:
    return json.loads((ROOT / "examples" / "decision-cases" / "low-risk-pass.json").read_text(encoding="utf-8"))


@pytest.fixture
def repository(tmp_path: Path) -> SqliteDecisionRepository:
    repo = SqliteDecisionRepository(tmp_path / "api.db")
    repo.initialize()
    return repo


def test_same_decision_id_is_isolated_between_tenants(repository: SqliteDecisionRepository) -> None:
    tenant_a, tenant_b = TenantContext("tenant-a"), TenantContext("tenant-b")
    first, second = example(), example()
    first["title"], second["title"] = "Tenant A", "Tenant B"
    repository.create_decision(tenant_a, first)
    repository.create_decision(tenant_b, second)
    assert repository.get_decision(tenant_a, first["decision_id"])["title"] == "Tenant A"
    assert repository.get_decision(tenant_b, second["decision_id"])["title"] == "Tenant B"


def test_cross_tenant_lookup_fails_closed(repository: SqliteDecisionRepository) -> None:
    repository.create_decision(TenantContext("tenant-a"), example())
    assert repository.get_decision(TenantContext("tenant-b"), example()["decision_id"]) is None


def test_update_and_audit_are_atomic_and_tenant_scoped(repository: SqliteDecisionRepository) -> None:
    tenant = TenantContext("tenant-a")
    document = example()
    repository.create_decision(tenant, document)
    document["status"] = "VALIDATION"
    event = {"event_id": "event-1", "event_type": "status.transitioned"}
    report = {"report_id": "report-1", "outcome": "PASS"}
    repository.save_result(tenant, document, report, [event])
    assert repository.get_decision(tenant, document["decision_id"])["status"] == "VALIDATION"
    assert repository.get_report(tenant, document["decision_id"]) == report
    assert repository.list_audit(tenant, document["decision_id"], limit=10, offset=0) == [event]
    assert repository.list_audit(TenantContext("tenant-b"), document["decision_id"], limit=10, offset=0) == []


def test_idempotency_replays_same_hash_and_rejects_changed_payload(repository: SqliteDecisionRepository) -> None:
    tenant = TenantContext("tenant-a")
    repository.store_idempotency(tenant, "actor", "create", "key-1", "hash-a", 201, {"ok": True})
    assert repository.get_idempotency(tenant, "actor", "create", "key-1", "hash-a") == (201, {"ok": True})
    with pytest.raises(IdempotencyConflict):
        repository.get_idempotency(tenant, "actor", "create", "key-1", "hash-b")


def test_pagination_is_bounded(repository: SqliteDecisionRepository) -> None:
    with pytest.raises(ValueError, match="INVALID_PAGE_LIMIT"):
        repository.list_audit(TenantContext("tenant-a"), "D-1", limit=101, offset=0)
