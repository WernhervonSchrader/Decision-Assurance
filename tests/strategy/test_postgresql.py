from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from decision_assurance.identity import ActorKind, Identity, Role
from decision_assurance.persistence.postgresql import (
    PostgresConnectionProvider,
    PostgresMigrationRunner,
    PostgresSettings,
)
from decision_assurance.production.contracts import SecretValue
from decision_assurance.strategy.store import PostgresStrategyStore
from decision_assurance.tenancy import TenantContext

from .test_adapter import ROOT, artifact, envelope

pytestmark = pytest.mark.postgresql


@pytest.fixture
def postgres_environment():
    dsn = os.getenv("DA_TEST_POSTGRES_DSN")
    if not dsn:
        if os.getenv("CI"):
            pytest.fail("DA_TEST_POSTGRES_DSN_REQUIRED_IN_CI")
        pytest.skip("Strategy PostgreSQL tests require an isolated DA_TEST_POSTGRES_DSN")
    with psycopg.connect(dsn, autocommit=True) as owner:
        owner.execute((ROOT / "migrations/postgresql/roles.sql").read_text(encoding="utf-8"))
    PostgresMigrationRunner(PostgresSettings(SecretValue(dsn))).migrate()

    class ApplicationConnections(PostgresConnectionProvider):
        def _connect(self, *, autocommit=False):
            connection = super()._connect(autocommit=autocommit)
            connection.execute("SET ROLE decision_assurance_application")
            connection.commit()  # Establish role before provider opens its transaction.
            return connection

    connections = ApplicationConnections(PostgresSettings(SecretValue(dsn)))
    store = PostgresStrategyStore(connections)
    document = json.loads(
        (ROOT / "examples/decision-cases/low-risk-pass.json").read_text(encoding="utf-8")
    )
    document["decision_id"] = "DECISION-ORIGINAL"
    document["audit_events"] = []
    with psycopg.connect(dsn, autocommit=True) as owner:
        owner.execute(
            "DELETE FROM audit_events WHERE tenant_id IN ('strategy-pg-a','strategy-pg-b')"
        )
        owner.execute("DELETE FROM decisions WHERE tenant_id IN ('strategy-pg-a','strategy-pg-b')")
        owner.execute(
            "INSERT INTO decisions (tenant_id,decision_id,document_json) VALUES (%s,%s,%s::jsonb)",
            ("strategy-pg-a", document["decision_id"], json.dumps(document)),
        )
    identity = Identity(
        "generator", TenantContext("strategy-pg-a"), Role.GENERATOR, ActorKind.AGENT
    )
    yield dsn, store, document, identity
    with psycopg.connect(dsn, autocommit=True) as owner:
        owner.execute(
            "DELETE FROM audit_events WHERE tenant_id IN ('strategy-pg-a','strategy-pg-b')"
        )
        owner.execute("DELETE FROM decisions WHERE tenant_id IN ('strategy-pg-a','strategy-pg-b')")


def test_postgresql_transaction_replay_and_forced_rls(postgres_environment):
    dsn, store, document, identity = postgres_environment
    request = envelope(document, tenant_id=identity.tenant.tenant_id)
    assert store.preview(identity, request)["complete_semantic_replay"] is False
    receipt = store.import_artifact(identity, request, "pg-import")
    assert store.import_artifact(identity, request, "pg-retry") == receipt
    assert store.get(identity, artifact()["id"])["original"] == request.artifact
    other = Identity("other", TenantContext("strategy-pg-b"), Role.GENERATOR, ActorKind.AGENT)
    assert store.get(other, artifact()["id"]) is None
    with psycopg.connect(dsn, autocommit=True) as application:
        application.execute("SET ROLE decision_assurance_application")
        assert application.execute("SELECT artifact_id FROM strategy_records").fetchall() == []
        application.execute(
            "SELECT set_config('decision_assurance.tenant_id','strategy-pg-b',false)"
        )
        assert application.execute("SELECT artifact_id FROM strategy_records").fetchall() == []
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            application.execute(
                "INSERT INTO strategy_records (tenant_id,artifact_id,decision_id,mode,request_hash,record_json) VALUES ('strategy-pg-a','forged','DECISION-ORIGINAL','baseline','hash','{}')"
            )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            application.execute("UPDATE strategy_records SET record_json='{}'")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            application.execute("DELETE FROM strategy_events")


def test_postgresql_audit_failure_rolls_back(postgres_environment):
    dsn, store, document, identity = postgres_environment
    # Test double fails inside the same real PostgreSQL transaction, after case/baseline writes.
    original_insert = store._insert

    def fail_final_insert(session, tenant, record):
        if record["mode"] == "draft":
            raise RuntimeError("synthetic audit/storage failure")
        original_insert(session, tenant, record)

    store._insert = fail_final_insert
    with pytest.raises(RuntimeError):
        store.import_artifact(
            identity, envelope(document, tenant_id=identity.tenant.tenant_id), "pg-rollback"
        )
    assert store.get(identity, "B-ORIGINAL") is None
    with psycopg.connect(dsn) as owner:
        assert (
            owner.execute(
                "SELECT document_json FROM decisions WHERE tenant_id=%s AND decision_id=%s",
                (identity.tenant.tenant_id, document["decision_id"]),
            ).fetchone()[0]
            == document
        )


def test_postgresql_concurrent_retries_create_one_audit_event(postgres_environment):
    dsn, store, document, identity = postgres_environment
    request = envelope(document, tenant_id=identity.tenant.tenant_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(
            pool.map(lambda _: store.import_artifact(identity, request, "concurrent"), range(2))
        )
    assert receipts[0] == receipts[1]
    with psycopg.connect(dsn) as owner:
        assert owner.execute(
            "SELECT count(*) FROM audit_events WHERE tenant_id=%s", (identity.tenant.tenant_id,)
        ).fetchone() == (1,)


@pytest.mark.parametrize("terminal", ["APPROVED", "BLOCKED"])
def test_postgresql_historical_observation_preserves_terminal_case(postgres_environment, terminal):
    dsn, store, document, identity = postgres_environment
    baseline = artifact()["baseline"]
    store.import_artifact(
        identity,
        envelope(
            document,
            tenant_id=identity.tenant.tenant_id,
            mode="baseline",
            artifact=baseline,
            selected_option_id=None,
        ),
        "baseline",
    )
    # Synthetic history; this fixture does not grant approval or execute an action.
    document["status"] = terminal
    with psycopg.connect(dsn) as owner:
        owner.execute(
            "UPDATE decisions SET document_json=%s::jsonb WHERE tenant_id=%s AND decision_id=%s",
            (json.dumps(document), identity.tenant.tenant_id, document["decision_id"]),
        )
    store.import_artifact(
        identity,
        envelope(
            document,
            tenant_id=identity.tenant.tenant_id,
            mode="observation",
            selected_option_id=None,
        ),
        "observation",
    )
    assert store.get(identity, baseline["id"])["binding"]["status"] == "DRAFT"
    with psycopg.connect(dsn) as owner:
        assert (
            owner.execute(
                "SELECT document_json FROM decisions WHERE tenant_id=%s AND decision_id=%s",
                (identity.tenant.tenant_id, document["decision_id"]),
            ).fetchone()[0]
            == document
        )
    rejected = envelope(document, tenant_id=identity.tenant.tenant_id)
    rejected.artifact["id"] = "STR-MUTATE-TERMINAL"
    with pytest.raises(ValueError, match="NOT_DRAFT"):
        store.import_artifact(identity, rejected, "prohibited")
