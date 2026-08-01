from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import TYPE_CHECKING, Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from ..persistence.postgresql import PostgresConnectionProvider
from ..production.contracts import JobPolicy, JobStatus, ResearchJob
from ..tenancy import TenantContext
from ..web_research.codec import run_from_data, to_data
from ..web_research.contracts import ResearchRun
from .contracts import ClaimedJob, LeaseToken
from .lifecycle import retry_delay

if TYPE_CHECKING:
    from ..web_research.service import SubmittedResearch


class JobConflict(ValueError):
    pass


class LeaseRejected(PermissionError):
    pass


class PostgresJobRepository:
    def __init__(self, connections: PostgresConnectionProvider, policy: JobPolicy | None = None):
        self._connections = connections
        self._policy = policy or JobPolicy()

    def enqueue(self, tenant: TenantContext, job: ResearchJob) -> ResearchJob:
        if tenant.tenant_id != job.tenant_id or job.status is not JobStatus.QUEUED:
            raise ValueError("INVALID_JOB_ENQUEUE")
        with self._connections.tenant_connection(tenant) as connection:
            inserted = connection.execute(
                """
                INSERT INTO research_jobs (
                    tenant_id, job_id, research_run_id, correlation_id, payload_hash,
                    status, attempt_count, available_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, research_run_id) DO NOTHING
                """,
                (
                    tenant.tenant_id,
                    job.job_id,
                    job.research_run_id,
                    job.correlation_id,
                    job.payload_hash,
                    job.status.value,
                    job.attempt_count,
                    job.available_at,
                    job.created_at,
                    job.updated_at,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM research_jobs
                WHERE tenant_id = %s AND research_run_id = %s
                FOR UPDATE
                """,
                (tenant.tenant_id, job.research_run_id),
            ).fetchone()
            if row is None:
                raise RuntimeError("JOB_ENQUEUE_CONVERGENCE_FAILED")
            existing = self._row_to_job(row)
            if existing.payload_hash != job.payload_hash:
                raise JobConflict("JOB_PAYLOAD_CONFLICT")
            if inserted.rowcount == 1:
                self._append_event(connection, existing, "JOB_QUEUED", job.updated_at)
            return existing

    def requeue(
        self,
        tenant: TenantContext,
        job_id: str,
        correlation_id: str,
        *,
        now: str,
    ) -> ResearchJob:
        """Atomically requeue one terminal job for an explicit domain-approved retry."""
        with self._connections.tenant_connection(tenant) as connection:
            row = connection.execute(
                """
                UPDATE research_jobs
                SET status = 'QUEUED',
                    correlation_id = %s,
                    attempt_count = 0,
                    available_at = %s::timestamptz,
                    lease_token_hash = NULL,
                    lease_expires_at = NULL,
                    last_error_code = NULL,
                    updated_at = %s::timestamptz
                WHERE tenant_id = %s AND job_id = %s
                  AND status IN ('COMPLETED', 'PARTIAL', 'FAILED', 'DEAD_LETTER')
                RETURNING *
                """,
                (correlation_id, now, now, tenant.tenant_id, job_id),
            ).fetchone()
            if row is None:
                exists = connection.execute(
                    """
                    SELECT 1 FROM research_jobs
                    WHERE tenant_id = %s AND job_id = %s
                    """,
                    (tenant.tenant_id, job_id),
                ).fetchone()
                if exists is None:
                    raise KeyError("JOB_NOT_FOUND")
                raise ValueError("JOB_NOT_RETRYABLE")
            job = self._row_to_job(row)
            self._append_event(connection, job, "JOB_REQUEUED", now)
            return job

    def submit(
        self, tenant: TenantContext, run: ResearchRun, job: ResearchJob
    ) -> SubmittedResearch:
        """Atomically persist a proposed Research run, budget row, queue job and queue audit."""
        from ..web_research.service import SubmittedResearch

        if tenant.tenant_id != run.tenant_id or tenant.tenant_id != job.tenant_id:
            raise ValueError("TENANT_MISMATCH")
        if run.research_run_id != job.research_run_id or job.status is not JobStatus.QUEUED:
            raise ValueError("INVALID_RESEARCH_JOB_SUBMISSION")
        with self._connections.tenant_connection(tenant) as connection:
            inserted_run = connection.execute(
                """
                INSERT INTO research_runs (
                    tenant_id, research_run_id, decision_file_id, semantic_fingerprint,
                    status, run_json, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, semantic_fingerprint) DO NOTHING
                """,
                (
                    tenant.tenant_id,
                    run.research_run_id,
                    run.request.decision_file_id,
                    run.semantic_fingerprint,
                    run.status.value,
                    Jsonb(to_data(run)),
                    run.created_at,
                    run.updated_at,
                ),
            )
            run_row = connection.execute(
                """
                SELECT run_json FROM research_runs
                WHERE tenant_id = %s AND semantic_fingerprint = %s
                FOR UPDATE
                """,
                (tenant.tenant_id, run.semantic_fingerprint),
            ).fetchone()
            if run_row is None:
                raise RuntimeError("RESEARCH_SUBMISSION_CONVERGENCE_FAILED")
            stored_run = run_from_data(dict(run_row["run_json"]))
            if inserted_run.rowcount == 1:
                connection.execute(
                    """
                    INSERT INTO research_budget_usage
                        (tenant_id, research_run_id, used_units)
                    VALUES (%s, %s, 0)
                    """,
                    (tenant.tenant_id, stored_run.research_run_id),
                )
            inserted_job = connection.execute(
                """
                INSERT INTO research_jobs (
                    tenant_id, job_id, research_run_id, correlation_id, payload_hash,
                    status, attempt_count, available_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, research_run_id) DO NOTHING
                """,
                (
                    tenant.tenant_id,
                    job.job_id,
                    stored_run.research_run_id,
                    job.correlation_id,
                    job.payload_hash,
                    job.status.value,
                    job.attempt_count,
                    job.available_at,
                    job.created_at,
                    job.updated_at,
                ),
            )
            job_row = connection.execute(
                """
                SELECT * FROM research_jobs
                WHERE tenant_id = %s AND research_run_id = %s
                FOR UPDATE
                """,
                (tenant.tenant_id, stored_run.research_run_id),
            ).fetchone()
            if job_row is None:
                raise RuntimeError("JOB_SUBMISSION_CONVERGENCE_FAILED")
            stored_job = self._row_to_job(job_row)
            if stored_job.payload_hash != job.payload_hash:
                raise JobConflict("JOB_PAYLOAD_CONFLICT")
            if inserted_job.rowcount == 1:
                self._append_event(connection, stored_job, "JOB_QUEUED", job.updated_at)
            return SubmittedResearch(
                stored_run,
                stored_job,
                replayed=inserted_run.rowcount != 1 or inserted_job.rowcount != 1,
            )

    def claim(self, worker_id: str, *, now: str) -> ClaimedJob | None:
        if not worker_id.strip():
            raise ValueError("INVALID_WORKER_ID")
        lease = LeaseToken(secrets.token_urlsafe(32))
        lease_hash = self._lease_hash(lease)
        with self._connections.worker_connection() as connection:
            row = connection.execute(
                """
                WITH candidate AS (
                    SELECT job.tenant_id, job.job_id
                    FROM research_jobs AS job
                    WHERE job.status IN ('QUEUED', 'RETRY_WAIT')
                      AND job.available_at <= %s::timestamptz
                      AND (
                          SELECT count(*) FROM research_jobs AS active
                          WHERE active.tenant_id = job.tenant_id
                            AND active.status = 'RUNNING'
                      ) < COALESCE((
                          SELECT limits.max_concurrent_jobs
                          FROM tenant_runtime_limits AS limits
                          WHERE limits.tenant_id = job.tenant_id
                      ), 2)
                    ORDER BY job.available_at, job.created_at, job.tenant_id, job.job_id
                    FOR UPDATE OF job SKIP LOCKED
                    LIMIT 1
                )
                UPDATE research_jobs AS job
                SET status = 'RUNNING',
                    attempt_count = job.attempt_count + 1,
                    lease_token_hash = %s,
                    lease_expires_at = %s::timestamptz + (%s * interval '1 second'),
                    updated_at = %s::timestamptz
                FROM candidate
                WHERE job.tenant_id = candidate.tenant_id AND job.job_id = candidate.job_id
                RETURNING job.*
                """,
                (now, lease_hash, now, self._policy.lease_seconds, now),
            ).fetchone()
            if row is None:
                return None
            job = self._row_to_job(row)
            self._append_event(connection, job, "JOB_CLAIMED", now, worker_id=worker_id)
            return ClaimedJob(job, lease)

    def heartbeat(
        self,
        tenant: TenantContext,
        job_id: str,
        lease_token: LeaseToken,
        *,
        now: str,
    ) -> None:
        with self._connections.worker_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE research_jobs
                SET lease_expires_at = %s::timestamptz + (%s * interval '1 second'),
                    updated_at = %s::timestamptz
                WHERE tenant_id = %s AND job_id = %s AND status = 'RUNNING'
                  AND lease_token_hash = %s
                  AND lease_expires_at > %s::timestamptz
                """,
                (
                    now,
                    self._policy.lease_seconds,
                    now,
                    tenant.tenant_id,
                    job_id,
                    self._lease_hash(lease_token),
                    now,
                ),
            )
            if cursor.rowcount != 1:
                raise LeaseRejected("INVALID_OR_EXPIRED_LEASE")

    def complete(
        self,
        tenant: TenantContext,
        job_id: str,
        lease_token: LeaseToken,
        *,
        partial: bool,
        now: str,
    ) -> None:
        target = JobStatus.PARTIAL if partial else JobStatus.COMPLETED
        with self._connections.worker_connection() as connection:
            row = connection.execute(
                """
                UPDATE research_jobs
                SET status = %s, lease_token_hash = NULL, lease_expires_at = NULL,
                    updated_at = %s::timestamptz
                WHERE tenant_id = %s AND job_id = %s AND status = 'RUNNING'
                  AND lease_token_hash = %s AND lease_expires_at > %s::timestamptz
                RETURNING *
                """,
                (
                    target.value,
                    now,
                    tenant.tenant_id,
                    job_id,
                    self._lease_hash(lease_token),
                    now,
                ),
            ).fetchone()
            if row is None:
                raise LeaseRejected("INVALID_OR_EXPIRED_LEASE")
            self._append_event(connection, self._row_to_job(row), f"JOB_{target.value}", now)

    def fail(
        self,
        tenant: TenantContext,
        job_id: str,
        lease_token: LeaseToken,
        reason_code: str,
        *,
        retryable: bool,
        now: str,
    ) -> None:
        if not reason_code or len(reason_code) > 128:
            raise ValueError("INVALID_JOB_FAILURE_REASON")
        with self._connections.worker_connection() as connection:
            current = connection.execute(
                """
                SELECT * FROM research_jobs
                WHERE tenant_id = %s AND job_id = %s AND status = 'RUNNING'
                  AND lease_token_hash = %s AND lease_expires_at > %s::timestamptz
                FOR UPDATE
                """,
                (tenant.tenant_id, job_id, self._lease_hash(lease_token), now),
            ).fetchone()
            if current is None:
                raise LeaseRejected("INVALID_OR_EXPIRED_LEASE")
            attempt_count = int(current["attempt_count"])
            if retryable and attempt_count < self._policy.max_attempts:
                target = JobStatus.RETRY_WAIT
                delay = retry_delay(self._policy, attempt_count)
            elif retryable:
                target = JobStatus.DEAD_LETTER
                delay = 0
            else:
                target = JobStatus.FAILED
                delay = 0
            row = connection.execute(
                """
                UPDATE research_jobs
                SET status = %s,
                    available_at = %s::timestamptz + (%s * interval '1 second'),
                    lease_token_hash = NULL,
                    lease_expires_at = NULL,
                    last_error_code = %s,
                    updated_at = %s::timestamptz
                WHERE tenant_id = %s AND job_id = %s
                RETURNING *
                """,
                (target.value, now, delay, reason_code, now, tenant.tenant_id, job_id),
            ).fetchone()
            if row is None:
                raise RuntimeError("JOB_FAILURE_UPDATE_FAILED")
            self._append_event(
                connection,
                self._row_to_job(row),
                f"JOB_{target.value}",
                now,
                reason_code=reason_code,
            )

    def cancel(self, tenant: TenantContext, job_id: str, *, now: str) -> ResearchJob:
        with self._connections.tenant_connection(tenant) as connection:
            current = connection.execute(
                """
                SELECT * FROM research_jobs
                WHERE tenant_id = %s AND job_id = %s
                FOR UPDATE
                """,
                (tenant.tenant_id, job_id),
            ).fetchone()
            if current is None:
                raise KeyError("JOB_NOT_FOUND")
            job = self._row_to_job(current)
            if job.status in {
                JobStatus.COMPLETED,
                JobStatus.PARTIAL,
                JobStatus.FAILED,
                JobStatus.DEAD_LETTER,
                JobStatus.CANCELLED,
            }:
                return job
            row = connection.execute(
                """
                UPDATE research_jobs
                SET status = 'CANCELLED', lease_token_hash = NULL, lease_expires_at = NULL,
                    updated_at = %s::timestamptz
                WHERE tenant_id = %s AND job_id = %s
                RETURNING *
                """,
                (now, tenant.tenant_id, job_id),
            ).fetchone()
            if row is None:
                raise RuntimeError("JOB_CANCELLATION_FAILED")
            cancelled = self._row_to_job(row)
            self._append_event(connection, cancelled, "JOB_CANCELLED", now)
            return cancelled

    def recover_stale(self, *, now: str) -> int:
        recovered = 0
        with self._connections.worker_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM research_jobs
                WHERE status = 'RUNNING' AND lease_expires_at <= %s::timestamptz
                ORDER BY lease_expires_at
                FOR UPDATE SKIP LOCKED
                """,
                (now,),
            ).fetchall()
            for current in rows:
                attempt_count = int(current["attempt_count"])
                if attempt_count < self._policy.max_attempts:
                    target = JobStatus.RETRY_WAIT
                    delay = retry_delay(self._policy, attempt_count)
                else:
                    target = JobStatus.DEAD_LETTER
                    delay = 0
                row = connection.execute(
                    """
                    UPDATE research_jobs
                    SET status = %s,
                        available_at = %s::timestamptz + (%s * interval '1 second'),
                        lease_token_hash = NULL,
                        lease_expires_at = NULL,
                        last_error_code = 'STALE_LEASE_RECOVERED',
                        updated_at = %s::timestamptz
                    WHERE tenant_id = %s AND job_id = %s
                    RETURNING *
                    """,
                    (
                        target.value,
                        now,
                        delay,
                        now,
                        current["tenant_id"],
                        current["job_id"],
                    ),
                ).fetchone()
                if row is not None:
                    recovered += 1
                    self._append_event(
                        connection,
                        self._row_to_job(row),
                        "JOB_STALE_LEASE_RECOVERED",
                        now,
                    )
        return recovered

    def is_cancelled(self, tenant: TenantContext, job_id: str) -> bool:
        with self._connections.tenant_connection(tenant) as connection:
            row = connection.execute(
                """
                SELECT status FROM research_jobs
                WHERE tenant_id = %s AND job_id = %s
                """,
                (tenant.tenant_id, job_id),
            ).fetchone()
        return row is not None and row["status"] == JobStatus.CANCELLED.value

    def queued_count(self) -> int:
        """Return the measured global worker backlog without exposing tenant labels."""
        with self._connections.worker_connection() as connection:
            row = connection.execute("SELECT da_research_queue_depth() AS queued_count").fetchone()
        if row is None:
            raise RuntimeError("JOB_QUEUE_MEASUREMENT_FAILED")
        return int(row["queued_count"])

    @staticmethod
    def _lease_hash(token: LeaseToken) -> str:
        return "sha256:" + hashlib.sha256(token.value.encode("utf-8")).hexdigest()

    @staticmethod
    def _row_to_job(row: dict[str, Any]) -> ResearchJob:
        return ResearchJob(
            job_id=str(row["job_id"]),
            tenant_id=str(row["tenant_id"]),
            research_run_id=str(row["research_run_id"]),
            correlation_id=str(row["correlation_id"]),
            payload_hash=str(row["payload_hash"]),
            status=JobStatus(str(row["status"])),
            attempt_count=int(row["attempt_count"]),
            available_at=PostgresJobRepository._timestamp(row["available_at"]),
            created_at=PostgresJobRepository._timestamp(row["created_at"]),
            updated_at=PostgresJobRepository._timestamp(row["updated_at"]),
            lease_token_hash=(
                None if row["lease_token_hash"] is None else str(row["lease_token_hash"])
            ),
            lease_expires_at=(
                None
                if row["lease_expires_at"] is None
                else PostgresJobRepository._timestamp(row["lease_expires_at"])
            ),
        )

    @staticmethod
    def _timestamp(value: object) -> str:
        if isinstance(value, datetime):
            return value.isoformat().replace("+00:00", "Z")
        return str(value)

    @staticmethod
    def _append_event(
        connection: Connection[dict[str, Any]],
        job: ResearchJob,
        event_type: str,
        occurred_at: str,
        *,
        worker_id: str | None = None,
        reason_code: str | None = None,
    ) -> None:
        sequence_row = connection.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) AS value
            FROM research_job_events
            WHERE tenant_id = %s AND job_id = %s
            """,
            (job.tenant_id, job.job_id),
        ).fetchone()
        sequence = 1 if sequence_row is None else int(sequence_row["value"]) + 1
        event_id = f"{job.job_id}:{sequence}"
        event = {
            "event_id": event_id,
            "event_type": event_type,
            "job_id": job.job_id,
            "research_run_id": job.research_run_id,
            "tenant_id": job.tenant_id,
            "correlation_id": job.correlation_id,
            "occurred_at": occurred_at,
            "worker_id": worker_id,
            "reason_code": reason_code,
        }
        connection.execute(
            """
            INSERT INTO research_job_events (
                tenant_id, job_id, event_id, sequence, event_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s::timestamptz)
            ON CONFLICT (tenant_id, job_id, event_id) DO NOTHING
            """,
            (job.tenant_id, job.job_id, event_id, sequence, Jsonb(event), occurred_at),
        )
