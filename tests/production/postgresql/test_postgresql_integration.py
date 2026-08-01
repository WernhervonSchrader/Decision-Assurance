from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier

import psycopg
import pytest
from psycopg import Connection

from decision_assurance.jobs.contracts import LeaseToken
from decision_assurance.jobs.postgresql import LeaseRejected, PostgresJobRepository
from decision_assurance.persistence.postgresql import (
    MigrationIntegrityError,
    PostgresConnectionProvider,
    PostgresMigrationRunner,
    PostgresSettings,
)
from decision_assurance.production.contracts import JobPolicy, JobStatus, ResearchJob, SecretValue
from decision_assurance.tenancy import TenantContext
from decision_assurance.web_research.contracts import ResearchRequest, ResearchRun, ResearchStatus
from decision_assurance.web_research.postgresql_repository import PostgresResearchRepository
from decision_assurance.web_research.repository import ResearchIdempotencyInProgress

ROOT = Path(__file__).parents[3]
MIGRATIONS = ROOT / "migrations" / "postgresql"
pytestmark = pytest.mark.postgresql


@pytest.fixture(scope="module")
def postgres_dsn() -> str:
    value = os.getenv("DA_TEST_POSTGRES_DSN")
    if not value:
        if os.getenv("CI"):
            pytest.fail("DA_TEST_POSTGRES_DSN_REQUIRED_IN_CI")
        pytest.skip("PostgreSQL integration requires DA_TEST_POSTGRES_DSN")
    return value


@pytest.fixture(scope="module", autouse=True)
def migrated_database(postgres_dsn: str) -> Iterator[None]:
    with psycopg.connect(postgres_dsn, autocommit=True) as connection:
        connection.execute((MIGRATIONS / "roles.sql").read_text(encoding="utf-8"))
    runner = PostgresMigrationRunner(PostgresSettings(SecretValue(postgres_dsn)), MIGRATIONS)
    runner.migrate()
    yield


def test_migrations_are_repeatable_and_reach_expected_version(postgres_dsn: str) -> None:
    runner = PostgresMigrationRunner(PostgresSettings(SecretValue(postgres_dsn)), MIGRATIONS)

    runner.migrate()

    assert runner.current_version() == "004"


def test_failed_migration_rolls_back_without_advancing_ledger(
    postgres_dsn: str, tmp_path: Path
) -> None:
    for name in (
        "001_v0_4_baseline.sql",
        "002_production_foundation_v0_5.sql",
        "003_controlled_pilot_v0_8.sql",
        "004_deployment_evidence_v0_9.sql",
    ):
        shutil.copyfile(MIGRATIONS / name, tmp_path / name)
    (tmp_path / "005_invalid.sql").write_text(
        "CREATE TABLE migration_rollback_probe (value TEXT);\nNOT VALID SQL;\n",
        encoding="utf-8",
    )
    runner = PostgresMigrationRunner(PostgresSettings(SecretValue(postgres_dsn)), tmp_path)

    with pytest.raises(psycopg.Error):
        runner.migrate()

    with psycopg.connect(postgres_dsn) as connection:
        version = connection.execute("SELECT max(version) FROM schema_migrations").fetchone()
        probe = connection.execute(
            "SELECT to_regclass('public.migration_rollback_probe')"
        ).fetchone()
    assert version == ("004",)
    assert probe == (None,)


def test_applied_migration_checksum_drift_is_rejected(postgres_dsn: str, tmp_path: Path) -> None:
    for name in ("001_v0_4_baseline.sql", "002_production_foundation_v0_5.sql"):
        shutil.copyfile(MIGRATIONS / name, tmp_path / name)
    first = tmp_path / "001_v0_4_baseline.sql"
    first.write_text(first.read_text(encoding="utf-8") + "\n-- drift\n", encoding="utf-8")
    runner = PostgresMigrationRunner(PostgresSettings(SecretValue(postgres_dsn)), tmp_path)

    with pytest.raises(MigrationIntegrityError, match="CHECKSUM_MISMATCH"):
        runner.migrate()


def _as_role(connection: Connection[tuple[object, ...]], role: str, tenant_id: str) -> None:
    connection.execute(f"SET ROLE {role}")  # noqa: S608 - fixed test-only role names
    connection.execute(
        "SELECT set_config('decision_assurance.tenant_id', %s, false)",
        (tenant_id,),
    )


def test_application_role_cannot_read_or_write_across_tenants(postgres_dsn: str) -> None:
    with psycopg.connect(postgres_dsn, autocommit=True) as owner:
        owner.execute("DELETE FROM decisions WHERE tenant_id IN ('rls-tenant-a', 'rls-tenant-b')")
        owner.execute(
            """
            INSERT INTO decisions (tenant_id, decision_id, document_json)
            VALUES ('rls-tenant-a', 'decision-a', '{}'),
                   ('rls-tenant-b', 'decision-b', '{}')
            """
        )

    with psycopg.connect(postgres_dsn, autocommit=True) as application:
        _as_role(application, "decision_assurance_application", "rls-tenant-a")
        visible = application.execute(
            "SELECT tenant_id FROM decisions ORDER BY tenant_id"
        ).fetchall()
        updated = application.execute(
            "UPDATE decisions SET document_json = '{\"changed\": true}' "
            "WHERE tenant_id = 'rls-tenant-b'"
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            application.execute(
                "INSERT INTO decisions (tenant_id, decision_id, document_json) "
                "VALUES ('rls-tenant-b', 'cross-tenant', '{}')"
            )

    assert visible == [("rls-tenant-a",)]
    assert updated.rowcount == 0


def test_no_tenant_context_is_fail_closed(postgres_dsn: str) -> None:
    with psycopg.connect(postgres_dsn, autocommit=True) as application:
        application.execute("SET ROLE decision_assurance_application")
        visible = application.execute("SELECT tenant_id FROM decisions").fetchall()

    assert visible == []


def test_runtime_roles_are_non_owner_and_cannot_bypass_rls(postgres_dsn: str) -> None:
    with psycopg.connect(postgres_dsn) as connection:
        rows = connection.execute(
            """
            SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls
            FROM pg_roles
            WHERE rolname IN (
                'decision_assurance_application',
                'decision_assurance_operations_readonly',
                'decision_assurance_audit_export'
            )
            """
        ).fetchall()
        ledger_privileges = connection.execute(
            "SELECT has_table_privilege('decision_assurance_application', "
            "'schema_migrations', 'INSERT,UPDATE,DELETE')"
        ).fetchone()

    assert len(rows) == 3
    assert all(not any(row[1:]) for row in rows)
    assert ledger_privileges == (False,)


def test_application_role_cannot_mutate_lifecycle_ledgers(postgres_dsn: str) -> None:
    with psycopg.connect(postgres_dsn, autocommit=True) as application:
        _as_role(application, "decision_assurance_application", "audit-tenant")
        for ledger in ("lifecycle_audit_events", "legal_hold_audit_events"):
            privileges = application.execute(
                "SELECT has_table_privilege(current_user, %s, 'SELECT,INSERT'), "
                "has_table_privilege(current_user, %s, 'UPDATE,DELETE')",
                (ledger, ledger),
            ).fetchone()
            assert privileges == (True, False)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                application.execute(f"DELETE FROM {ledger}")  # noqa: S608 - fixed table names


def _seed_job_run(connection: Connection[tuple[object, ...]], run_id: str) -> None:
    connection.execute(
        """
        INSERT INTO research_runs (
            tenant_id, research_run_id, decision_file_id, semantic_fingerprint,
            status, run_json, created_at, updated_at
        ) VALUES (
            'job-tenant', %s, %s, %s, 'CREATED', '{}',
            '2026-07-30T10:00:00Z', '2026-07-30T10:00:00Z'
        ) ON CONFLICT (tenant_id, research_run_id) DO NOTHING
        """,
        (run_id, f"decision-{run_id}", f"fingerprint-{run_id}"),
    )


def _research_job(job_id: str, run_id: str) -> ResearchJob:
    return ResearchJob(
        job_id=job_id,
        tenant_id="job-tenant",
        research_run_id=run_id,
        correlation_id=f"correlation-{job_id}",
        payload_hash="sha256:" + "a" * 64,
        status=JobStatus.QUEUED,
        attempt_count=0,
        available_at="2026-07-30T10:00:00Z",
        created_at="2026-07-30T10:00:00Z",
        updated_at="2026-07-30T10:00:00Z",
    )


def test_job_enqueue_claim_retry_lease_and_completion_are_atomic(postgres_dsn: str) -> None:
    with psycopg.connect(postgres_dsn, autocommit=True) as owner:
        owner.execute("DELETE FROM research_job_events WHERE tenant_id = 'job-tenant'")
        owner.execute("DELETE FROM research_jobs WHERE tenant_id = 'job-tenant'")
        _seed_job_run(owner, "run-job-1")
    connections = PostgresConnectionProvider(PostgresSettings(SecretValue(postgres_dsn)))
    repository = PostgresJobRepository(
        connections,
        JobPolicy(max_attempts=3, lease_seconds=60, base_backoff_seconds=5),
    )
    tenant = TenantContext("job-tenant")
    job = _research_job("job-1", "run-job-1")

    assert repository.enqueue(tenant, job) == job
    assert repository.enqueue(tenant, job) == job
    assert repository.queued_count() == 1
    with psycopg.connect(postgres_dsn) as application:
        application.execute("SET ROLE decision_assurance_application")
        assert application.execute("SELECT da_research_queue_depth()").fetchone() == (1,)
    claimed = repository.claim("worker-1", now="2026-07-30T10:00:00Z")
    assert claimed is not None
    assert claimed.job.status is JobStatus.RUNNING
    with pytest.raises(LeaseRejected):
        repository.complete(
            tenant,
            job.job_id,
            LeaseToken("incorrect-lease"),
            partial=False,
            now="2026-07-30T10:00:01Z",
        )
    repository.fail(
        tenant,
        job.job_id,
        claimed.lease_token,
        "PROVIDER_TIMEOUT",
        retryable=True,
        now="2026-07-30T10:00:01Z",
    )
    assert repository.claim("worker-1", now="2026-07-30T10:00:05Z") is None
    retried = repository.claim("worker-1", now="2026-07-30T10:00:06Z")
    assert retried is not None
    repository.complete(
        tenant,
        job.job_id,
        retried.lease_token,
        partial=False,
        now="2026-07-30T10:00:07Z",
    )
    assert repository.queued_count() == 0

    with psycopg.connect(postgres_dsn) as owner:
        status = owner.execute(
            "SELECT status, attempt_count FROM research_jobs "
            "WHERE tenant_id = 'job-tenant' AND job_id = 'job-1'"
        ).fetchone()
        event_count = owner.execute(
            "SELECT count(*) FROM research_job_events "
            "WHERE tenant_id = 'job-tenant' AND job_id = 'job-1'"
        ).fetchone()
    assert status == ("COMPLETED", 2)
    assert event_count == (5,)


def test_stale_lease_recovery_and_cancellation_prevent_delivery(postgres_dsn: str) -> None:
    with psycopg.connect(postgres_dsn, autocommit=True) as owner:
        owner.execute("DELETE FROM research_job_events WHERE tenant_id = 'job-tenant'")
        owner.execute("DELETE FROM research_jobs WHERE tenant_id = 'job-tenant'")
        _seed_job_run(owner, "run-job-stale")
        _seed_job_run(owner, "run-job-cancel")
    connections = PostgresConnectionProvider(PostgresSettings(SecretValue(postgres_dsn)))
    repository = PostgresJobRepository(connections, JobPolicy(lease_seconds=5))
    tenant = TenantContext("job-tenant")
    repository.enqueue(tenant, _research_job("job-stale", "run-job-stale"))
    repository.enqueue(tenant, _research_job("job-cancel", "run-job-cancel"))
    claimed = repository.claim("worker-1", now="2026-07-30T10:00:00Z")
    assert claimed is not None

    assert repository.recover_stale(now="2026-07-30T10:00:06Z") == 1
    cancelled = repository.cancel(tenant, "job-cancel", now="2026-07-30T10:00:07Z")
    assert cancelled.status is JobStatus.CANCELLED


def test_heartbeat_prevents_second_worker_claim_after_original_expiry(
    postgres_dsn: str,
) -> None:
    with psycopg.connect(postgres_dsn, autocommit=True) as owner:
        owner.execute("DELETE FROM research_job_events WHERE tenant_id = 'job-tenant'")
        owner.execute("DELETE FROM research_jobs WHERE tenant_id = 'job-tenant'")
        _seed_job_run(owner, "run-job-heartbeat")
    repository = PostgresJobRepository(
        PostgresConnectionProvider(PostgresSettings(SecretValue(postgres_dsn))),
        JobPolicy(lease_seconds=5),
    )
    tenant = TenantContext("job-tenant")
    repository.enqueue(tenant, _research_job("job-heartbeat", "run-job-heartbeat"))
    claimed = repository.claim("worker-1", now="2026-07-30T10:00:00Z")
    assert claimed is not None

    repository.heartbeat(
        tenant,
        claimed.job.job_id,
        claimed.lease_token,
        now="2026-07-30T10:00:04Z",
    )
    assert repository.recover_stale(now="2026-07-30T10:00:06Z") == 0
    assert repository.claim("worker-2", now="2026-07-30T10:00:06Z") is None
    repository.complete(
        tenant,
        claimed.job.job_id,
        claimed.lease_token,
        partial=False,
        now="2026-07-30T10:00:07Z",
    )


def test_two_workers_racing_for_one_job_have_exactly_one_lease(postgres_dsn: str) -> None:
    with psycopg.connect(postgres_dsn, autocommit=True) as owner:
        owner.execute("DELETE FROM research_job_events WHERE tenant_id = 'job-tenant'")
        owner.execute("DELETE FROM research_jobs WHERE tenant_id = 'job-tenant'")
        _seed_job_run(owner, "run-job-race")
    repository = PostgresJobRepository(
        PostgresConnectionProvider(PostgresSettings(SecretValue(postgres_dsn)))
    )
    tenant = TenantContext("job-tenant")
    repository.enqueue(tenant, _research_job("job-race", "run-job-race"))
    barrier = Barrier(2)

    def claim(worker_id: str) -> str | None:
        barrier.wait()
        claimed = repository.claim(worker_id, now="2026-07-30T10:00:00Z")
        return None if claimed is None else claimed.job.job_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = (
            pool.submit(claim, "worker-1"),
            pool.submit(claim, "worker-2"),
        )
        outcomes = [future.result() for future in futures]

    assert outcomes.count("job-race") == 1
    assert outcomes.count(None) == 1


def test_terminal_job_can_be_requeued_once_for_domain_approved_retry(
    postgres_dsn: str,
) -> None:
    with psycopg.connect(postgres_dsn, autocommit=True) as owner:
        owner.execute("DELETE FROM research_job_events WHERE tenant_id = 'job-tenant'")
        owner.execute("DELETE FROM research_jobs WHERE tenant_id = 'job-tenant'")
        _seed_job_run(owner, "run-job-requeue")
    repository = PostgresJobRepository(
        PostgresConnectionProvider(PostgresSettings(SecretValue(postgres_dsn)))
    )
    tenant = TenantContext("job-tenant")
    repository.enqueue(tenant, _research_job("job-requeue", "run-job-requeue"))
    claimed = repository.claim("worker-1", now="2026-07-30T10:00:00Z")
    assert claimed is not None
    repository.complete(
        tenant,
        claimed.job.job_id,
        claimed.lease_token,
        partial=True,
        now="2026-07-30T10:00:01Z",
    )

    queued = repository.requeue(
        tenant,
        claimed.job.job_id,
        "correlation-retry",
        now="2026-07-30T10:00:02Z",
    )
    assert queued.status is JobStatus.QUEUED
    assert queued.attempt_count == 0
    retried = repository.claim("worker-2", now="2026-07-30T10:00:02Z")
    assert retried is not None and retried.job.correlation_id == "correlation-retry"


def test_concurrent_postgresql_idempotency_has_one_owner(postgres_dsn: str) -> None:
    with psycopg.connect(postgres_dsn, autocommit=True) as owner:
        owner.execute("DELETE FROM research_idempotency WHERE tenant_id = 'atomic-tenant'")
    repository = PostgresResearchRepository(
        PostgresConnectionProvider(PostgresSettings(SecretValue(postgres_dsn)))
    )
    tenant = TenantContext("atomic-tenant")
    barrier = Barrier(2)

    def reserve() -> str:
        barrier.wait()
        try:
            result = repository.reserve_idempotency(
                tenant,
                "actor-1",
                "mcp:research_start",
                "same-key",
                "sha256:" + "b" * 64,
            )
        except ResearchIdempotencyInProgress:
            return "IN_PROGRESS"
        return "OWNER" if result is None else "REPLAY"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = (pool.submit(reserve), pool.submit(reserve))
        outcomes = sorted(future.result() for future in futures)

    assert outcomes == ["IN_PROGRESS", "OWNER"]


def test_worker_role_can_access_only_queue_owned_tables(postgres_dsn: str) -> None:
    with psycopg.connect(postgres_dsn, autocommit=True) as worker:
        worker.execute("SET ROLE decision_assurance_worker")
        worker.execute("SELECT count(*) FROM research_jobs").fetchone()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            worker.execute("SELECT count(*) FROM decisions").fetchone()


def _proposed_run(run_id: str, fingerprint: str) -> ResearchRun:
    return ResearchRun(
        research_run_id=run_id,
        tenant_id="atomic-tenant",
        actor_id="actor-1",
        request=ResearchRequest(
            decision_file_id=f"decision-{run_id}",
            claim_refs=("claim-1",),
            query="current public evidence",
            locale="en",
            preferred_languages=("en",),
        ),
        expected_document_hash="sha256:" + "c" * 64,
        semantic_fingerprint=fingerprint,
        status=ResearchStatus.CREATED,
        created_at="2026-07-30T10:00:00Z",
        updated_at="2026-07-30T10:00:00Z",
        correlation_id="correlation-atomic",
    )


def _clear_atomic_tenant(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as owner:
        owner.execute("DELETE FROM research_job_events WHERE tenant_id = 'atomic-tenant'")
        owner.execute("DELETE FROM research_jobs WHERE tenant_id = 'atomic-tenant'")
        owner.execute("DELETE FROM research_budget_usage WHERE tenant_id = 'atomic-tenant'")
        owner.execute("DELETE FROM research_runs WHERE tenant_id = 'atomic-tenant'")


@pytest.fixture
def clean_atomic_tenant(postgres_dsn: str) -> Iterator[None]:
    _clear_atomic_tenant(postgres_dsn)
    yield
    _clear_atomic_tenant(postgres_dsn)


def test_research_run_budget_job_and_queue_audit_submit_atomically(
    postgres_dsn: str, clean_atomic_tenant: None
) -> None:
    del clean_atomic_tenant
    repository = PostgresJobRepository(
        PostgresConnectionProvider(PostgresSettings(SecretValue(postgres_dsn)))
    )
    tenant = TenantContext("atomic-tenant")
    run = _proposed_run("run-atomic-1", "fingerprint-atomic-1")
    job = ResearchJob(
        job_id="job-atomic",
        tenant_id=tenant.tenant_id,
        research_run_id=run.research_run_id,
        correlation_id=run.correlation_id,
        payload_hash=run.expected_document_hash,
        status=JobStatus.QUEUED,
        attempt_count=0,
        available_at=run.created_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )

    first = repository.submit(tenant, run, job)
    replay = repository.submit(tenant, run, job)

    assert first.replayed is False
    assert replay.replayed is True
    with psycopg.connect(postgres_dsn) as owner:
        counts = owner.execute(
            """
            SELECT
                (SELECT count(*) FROM research_runs WHERE tenant_id = 'atomic-tenant'),
                (SELECT count(*) FROM research_budget_usage WHERE tenant_id = 'atomic-tenant'),
                (SELECT count(*) FROM research_jobs WHERE tenant_id = 'atomic-tenant'),
                (SELECT count(*) FROM research_job_events WHERE tenant_id = 'atomic-tenant')
            """
        ).fetchone()
    assert counts == (1, 1, 1, 1)

    conflicting_run = _proposed_run("run-atomic-2", "fingerprint-atomic-2")
    conflicting_job = replace(job, research_run_id=conflicting_run.research_run_id)
    with pytest.raises(psycopg.errors.UniqueViolation):
        repository.submit(tenant, conflicting_run, conflicting_job)
    with psycopg.connect(postgres_dsn) as owner:
        rolled_back = owner.execute(
            "SELECT count(*) FROM research_runs "
            "WHERE tenant_id = 'atomic-tenant' AND research_run_id = 'run-atomic-2'"
        ).fetchone()
    assert rolled_back == (0,)
