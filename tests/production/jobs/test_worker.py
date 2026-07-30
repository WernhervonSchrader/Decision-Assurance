from __future__ import annotations

from dataclasses import replace
from threading import Event

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
        self.calls.append(("complete", (partial, now)))

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
        self.calls.append(("fail", (reason_code, retryable, now)))

    def heartbeat(
        self,
        tenant: TenantContext,
        job_id: str,
        lease_token: LeaseToken,
        *,
        now: str,
    ) -> None:
        self.calls.append(("heartbeat", now))

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
        (lambda job, cancelled: False, ("complete", (False, "2026-07-30T10:00:09Z"))),
        (lambda job, cancelled: True, ("complete", (True, "2026-07-30T10:00:09Z"))),
        (
            lambda job, cancelled: (_ for _ in ()).throw(RetryableJobError("PROVIDER_TIMEOUT")),
            ("fail", ("PROVIDER_TIMEOUT", True, "2026-07-30T10:00:09Z")),
        ),
        (
            lambda job, cancelled: (_ for _ in ()).throw(NonRetryableJobError("POISONED_CONTENT")),
            ("fail", ("POISONED_CONTENT", False, "2026-07-30T10:00:09Z")),
        ),
    )
    for processor, expected in cases:
        claimed = ClaimedJob(_job(), LeaseToken("lease-secret"))
        repository = FakeJobs(claimed)
        worker = ResearchWorker(
            repository,
            processor,
            clock=lambda: "2026-07-30T10:00:09Z",
        )

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


def test_controlled_clock_advances_across_claim_heartbeat_and_completion() -> None:
    repository = FakeJobs(ClaimedJob(_job(), LeaseToken("lease-secret")))
    heartbeat_seen = Event()
    controlled_times = iter(
        (
            "2026-07-30T10:00:00Z",
            "2026-07-30T10:00:04Z",
            "2026-07-30T10:00:07Z",
        )
    )

    def clock() -> str:
        return next(controlled_times)

    def heartbeat(*args, **kwargs):  # type: ignore[no-untyped-def]
        del args
        repository.calls.append(("heartbeat", kwargs["now"]))
        heartbeat_seen.set()

    repository.heartbeat = heartbeat  # type: ignore[method-assign]

    def processor(job: ResearchJob, cancelled) -> bool:  # type: ignore[no-untyped-def]
        del job
        assert heartbeat_seen.wait(1)
        assert not cancelled()
        return False

    worker = ResearchWorker(
        repository,
        processor,
        clock=clock,
        heartbeat_interval_seconds=0.01,
    )

    assert worker.run_once("worker-1", now=clock())
    assert ("heartbeat", "2026-07-30T10:00:04Z") in repository.calls
    assert repository.calls[-1] == ("complete", (False, "2026-07-30T10:00:07Z"))


def test_lease_loss_stops_processing_without_terminal_write() -> None:
    repository = FakeJobs(ClaimedJob(_job(), LeaseToken("lease-secret")))

    def heartbeat(*args, **kwargs):  # type: ignore[no-untyped-def]
        del args, kwargs
        raise PermissionError("LEASE_LOST")

    repository.heartbeat = heartbeat  # type: ignore[method-assign]

    def processor(job: ResearchJob, cancelled) -> bool:  # type: ignore[no-untyped-def]
        del job
        for _ in range(100):
            if cancelled():
                return False
            Event().wait(0.01)
        raise AssertionError("lease loss was not observed")

    worker = ResearchWorker(
        repository,
        processor,
        clock=lambda: "2026-07-30T10:00:05Z",
        heartbeat_interval_seconds=0.01,
    )

    assert worker.run_once("worker-1", now="2026-07-30T10:00:00Z")
    assert not any(name in {"complete", "fail"} for name, _ in repository.calls)
