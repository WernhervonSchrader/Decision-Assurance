from __future__ import annotations

from dataclasses import replace

from decision_assurance.jobs.contracts import ClaimedJob, LeaseToken
from decision_assurance.jobs.worker import (
    NonRetryableJobError,
    ResearchWorker,
    RetryableJobError,
)
from decision_assurance.production.contracts import JobStatus, ResearchJob
from decision_assurance.tenancy import TenantContext


def _job() -> ResearchJob:
    return ResearchJob(
        job_id="job-1",
        tenant_id="tenant-a",
        research_run_id="run-1",
        correlation_id="correlation-1",
        payload_hash="sha256:" + "a" * 64,
        status=JobStatus.RUNNING,
        attempt_count=1,
        available_at="2026-07-30T10:00:00Z",
        created_at="2026-07-30T10:00:00Z",
        updated_at="2026-07-30T10:00:00Z",
        lease_token_hash="sha256:" + "b" * 64,
        lease_expires_at="2026-07-30T10:01:00Z",
    )


class FakeJobs:
    def __init__(self, claimed: ClaimedJob | None):
        self.claimed = claimed
        self.calls: list[tuple[str, object]] = []

    def claim(self, worker_id: str, *, now: str) -> ClaimedJob | None:
        self.calls.append(("claim", worker_id))
        result, self.claimed = self.claimed, None
        return result

    def complete(
        self,
        tenant: TenantContext,
        job_id: str,
        lease_token: LeaseToken,
        *,
        partial: bool,
        now: str,
    ) -> None:
        self.calls.append(("complete", partial))

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
        self.calls.append(("fail", (reason_code, retryable)))

    def is_cancelled(self, tenant: TenantContext, job_id: str) -> bool:
        return False


def test_idle_worker_does_not_invoke_processor() -> None:
    repository = FakeJobs(None)
    processor_calls = 0

    def processor(job: ResearchJob, cancelled: object) -> bool:
        nonlocal processor_calls
        processor_calls += 1
        return False

    worker = ResearchWorker(repository, processor)

    assert worker.run_once("worker-1", now="2026-07-30T10:00:00Z") is False
    assert processor_calls == 0


def test_success_partial_retryable_and_poison_failures_are_distinct() -> None:
    cases = (
        (lambda job, cancelled: False, ("complete", False)),
        (lambda job, cancelled: True, ("complete", True)),
        (
            lambda job, cancelled: (_ for _ in ()).throw(RetryableJobError("PROVIDER_TIMEOUT")),
            ("fail", ("PROVIDER_TIMEOUT", True)),
        ),
        (
            lambda job, cancelled: (_ for _ in ()).throw(NonRetryableJobError("POISONED_CONTENT")),
            ("fail", ("POISONED_CONTENT", False)),
        ),
    )
    for processor, expected in cases:
        claimed = ClaimedJob(_job(), LeaseToken("lease-secret"))
        repository = FakeJobs(claimed)
        worker = ResearchWorker(repository, processor)

        assert worker.run_once("worker-1", now="2026-07-30T10:00:00Z") is True
        assert repository.calls[-1] == expected


def test_cancelled_delivery_never_invokes_processor() -> None:
    job = replace(
        _job(),
        status=JobStatus.CANCELLED,
        lease_token_hash=None,
        lease_expires_at=None,
    )
    repository = FakeJobs(ClaimedJob(job, LeaseToken("lease-secret")))
    calls = 0

    def processor(job: ResearchJob, cancelled: object) -> bool:
        nonlocal calls
        calls += 1
        return False

    worker = ResearchWorker(repository, processor)

    assert worker.run_once("worker-1", now="2026-07-30T10:00:00Z") is True
    assert calls == 0
