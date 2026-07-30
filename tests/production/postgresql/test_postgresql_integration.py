from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

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

    assert runner.current_version() == "002"


def test_failed_migration_rolls_back_without_advancing_ledger(
    postgres_dsn: str, tmp_path: Path
) -> None:
    for name in ("001_v0_4_baseline.sql", "002_production_foundation_v0_5.sql"):
        shutil.copyfile(MIGRATIONS / name, tmp_path / name)
    (tmp_path / "003_invalid.sql").write_text(
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
    assert version == ("002",)
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


def test_research_run_budget_job_and_queue_audit_submit_atomically(postgres_dsn: str) -> None:
    with psycopg.connect(postgres_dsn, autocommit=True) as owner:
        owner.execute("DELETE FROM research_job_events WHERE tenant_id = 'atomic-tenant'")
        owner.execute("DELETE FROM research_jobs WHERE tenant_id = 'atomic-tenant'")
        owner.execute("DELETE FROM research_budget_usage WHERE tenant_id = 'atomic-tenant'")
        owner.execute("DELETE FROM research_runs WHERE tenant_id = 'atomic-tenant'")
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
