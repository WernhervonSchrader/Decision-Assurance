from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest

from decision_assurance.export.postgresql import PostgresExportRepository
from decision_assurance.export.service import ExportRejected, PilotExportService
from decision_assurance.export.validator import validate_export
from decision_assurance.identity import ActorKind, Identity, Role
from decision_assurance.lifecycle.postgresql import PostgresLifecycleRepository
from decision_assurance.lifecycle.service import PilotLifecycleService
from decision_assurance.persistence.postgresql import (
    PostgresConnectionProvider,
    PostgresMigrationRunner,
    PostgresSettings,
)
from decision_assurance.production.contracts import SecretValue
from decision_assurance.repositories.postgresql import PostgresDecisionRepository
from decision_assurance.tenancy import TenantContext

pytestmark = pytest.mark.postgresql
ROOT = Path(__file__).parents[3]
MIGRATIONS = ROOT / "migrations" / "postgresql"
NOW = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
TENANTS = ("pilot-lifecycle-a", "pilot-lifecycle-b")


@pytest.fixture(scope="module")
def postgres_dsn() -> str:
    value = os.getenv("DA_TEST_POSTGRES_DSN")
    if not value:
        if os.getenv("CI"):
            pytest.fail("DA_TEST_POSTGRES_DSN_REQUIRED_IN_CI")
        pytest.skip("PostgreSQL integration requires DA_TEST_POSTGRES_DSN")
    return value


@pytest.fixture(autouse=True)
def database(postgres_dsn: str) -> Iterator[None]:
    with psycopg.connect(postgres_dsn, autocommit=True) as connection:
        connection.execute((MIGRATIONS / "roles.sql").read_text(encoding="utf-8"))
    PostgresMigrationRunner(PostgresSettings(SecretValue(postgres_dsn)), MIGRATIONS).migrate()
    _clear(postgres_dsn)
    yield
    _clear(postgres_dsn)


def _clear(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as connection:
        statements = (
            "DELETE FROM lifecycle_audit_events WHERE tenant_id = ANY(%s)",
            "DELETE FROM deletion_requests WHERE tenant_id = ANY(%s)",
            "DELETE FROM legal_holds WHERE tenant_id = ANY(%s)",
            "DELETE FROM reports WHERE tenant_id = ANY(%s)",
            "DELETE FROM audit_events WHERE tenant_id = ANY(%s)",
            "DELETE FROM idempotency WHERE tenant_id = ANY(%s)",
            "DELETE FROM decisions WHERE tenant_id = ANY(%s)",
            "DELETE FROM tenant_retention_policies WHERE tenant_id = ANY(%s)",
        )
        for statement in statements:
            connection.execute(statement, (list(TENANTS),))


def _document(decision_id: str) -> dict[str, object]:
    return {
        "decision_id": decision_id,
        "status": "APPROVED",
        "outcome": "PASS",
        "created_by": {"id": "generator", "role": "GENERATOR", "kind": "HUMAN"},
        "claims": [],
        "evidence": [],
        "findings": [],
        "approvals": [{"actor": {"id": "approver", "role": "APPROVER", "kind": "HUMAN"}}],
        "audit_events": [],
    }


def test_postgresql_export_then_legal_hold_and_physical_delete(postgres_dsn: str) -> None:
    connections = PostgresConnectionProvider(PostgresSettings(SecretValue(postgres_dsn)))
    decisions = PostgresDecisionRepository(connections)
    tenant_a = TenantContext(TENANTS[0])
    tenant_b = TenantContext(TENANTS[1])
    decisions.create_decision(tenant_a, _document("quote-1"))
    decisions.create_decision(tenant_b, _document("quote-1"))
    actor = Identity("admin-a", tenant_a, Role.TENANT_ADMIN, ActorKind.HUMAN)
    lifecycle = PilotLifecycleService(
        PostgresLifecycleRepository(connections),
        SecretValue("postgres-lifecycle-pepper"),
        clock=lambda: NOW,
    )
    exporter = PilotExportService(
        PostgresExportRepository(connections),
        version="0.8.0",
        commit_sha="a" * 40,
        policy_versions={"sales-quote": "1"},
        clock=lambda: NOW,
    )

    archive = exporter.build(actor, "quote-1")
    assert validate_export(archive.content).valid
    with pytest.raises(ExportRejected, match="CASE_NOT_FOUND"):
        exporter.build(
            Identity("admin-a", TenantContext("not-a-tenant"), Role.TENANT_ADMIN, ActorKind.HUMAN),
            "quote-1",
        )

    lifecycle.place_legal_hold(actor, "quote-1", "LITIGATION", "correlation-1")
    request = lifecycle.request_deletion(
        actor, "quote-1", "USER_REQUEST", "delete-1", "correlation-1"
    )
    assert (
        lifecycle.execute_deletion(actor, request.request_id, "correlation-2").status.value
        == "BLOCKED_BY_HOLD"
    )
    assert decisions.get_decision(tenant_a, "quote-1") is not None

    assert lifecycle.release_legal_hold(actor, "quote-1", "correlation-3")
    completed = lifecycle.execute_deletion(actor, request.request_id, "correlation-4")
    assert completed.status.value == "COMPLETED"
    assert decisions.get_decision(tenant_a, "quote-1") is None
    assert decisions.get_decision(tenant_b, "quote-1") is not None
    with psycopg.connect(postgres_dsn) as connection:
        tombstone = connection.execute(
            "SELECT decision_id, status, case_ref_hash, actor_hash FROM deletion_requests "
            "WHERE tenant_id = %s AND request_id = %s",
            (tenant_a.tenant_id, request.request_id),
        ).fetchone()
        events = connection.execute(
            "SELECT event_type, previous_event_hash, event_hash FROM lifecycle_audit_events "
            "WHERE tenant_id = %s AND request_id = %s ORDER BY sequence",
            (tenant_a.tenant_id, request.request_id),
        ).fetchall()
    assert tombstone is not None and tombstone[0] is None and tombstone[1] == "COMPLETED"
    assert "quote-1" not in str(tombstone) and "admin-a" not in str(tombstone)
    assert [event[0] for event in events] == [
        "data.deletion-requested",
        "data.deletion-blocked",
        "data.deletion-executing",
        "data.deletion-completed",
    ]
    assert all(events[index][1] == events[index - 1][2] for index in range(1, len(events)))


def test_parallel_approval_and_delete_never_resurrects_case(postgres_dsn: str) -> None:
    connections = PostgresConnectionProvider(PostgresSettings(SecretValue(postgres_dsn)))
    decisions = PostgresDecisionRepository(connections)
    tenant = TenantContext(TENANTS[0])
    decisions.create_decision(tenant, _document("quote-race"))
    actor = Identity("admin-a", tenant, Role.TENANT_ADMIN, ActorKind.HUMAN)
    lifecycle = PilotLifecycleService(
        PostgresLifecycleRepository(connections),
        SecretValue("postgres-lifecycle-pepper"),
        clock=lambda: NOW,
    )
    deletion = lifecycle.request_deletion(
        actor, "quote-race", "USER_REQUEST", "race-delete", "correlation-race"
    )
    approved_document = _document("quote-race")

    def approve() -> str:
        try:
            decisions.save_result(tenant, approved_document, None, [])
        except KeyError:
            return "NOT_FOUND"
        return "SAVED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        approval = pool.submit(approve)
        executed = pool.submit(
            lifecycle.execute_deletion, actor, deletion.request_id, "correlation-race"
        )

    assert approval.result() in {"SAVED", "NOT_FOUND"}
    assert executed.result().status.value == "COMPLETED"
    assert decisions.get_decision(tenant, "quote-race") is None
