from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from threading import Event, Thread

from ..production.contracts import JobStatus, ResearchJob
from ..tenancy import TenantContext
from .repository import JobRepository


class RetryableJobError(RuntimeError):
    pass


class NonRetryableJobError(RuntimeError):
    pass


CancellationCheck = Callable[[], bool]
ResearchProcessor = Callable[[ResearchJob, CancellationCheck], bool]
Clock = Callable[[], str]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResearchWorker:
    def __init__(
        self,
        repository: JobRepository,
        processor: ResearchProcessor,
        *,
        clock: Clock = _utc_now,
        heartbeat_interval_seconds: float = 20.0,
    ):
        if heartbeat_interval_seconds <= 0:
            raise ValueError("INVALID_HEARTBEAT_INTERVAL")
        self._repository = repository
        self._processor = processor
        self._clock = clock
        self._heartbeat_interval_seconds = heartbeat_interval_seconds

    def run_once(self, worker_id: str, *, now: str) -> bool:
        claimed = self._repository.claim(worker_id, now=now)
        if claimed is None:
            return False
        job = claimed.job
        tenant = TenantContext(job.tenant_id)
        if job.status is JobStatus.CANCELLED:
            return True

        heartbeat_stop = Event()
        lease_lost = Event()

        def cancelled() -> bool:
            if lease_lost.is_set():
                return True
            try:
                return self._repository.is_cancelled(tenant, job.job_id)
            except Exception:
                lease_lost.set()
                return True

        def maintain_lease() -> None:
            while not heartbeat_stop.wait(self._heartbeat_interval_seconds):
                try:
                    self._repository.heartbeat(
                        tenant,
                        job.job_id,
                        claimed.lease_token,
                        now=self._clock(),
                    )
                except Exception:
                    lease_lost.set()
                    return

        if cancelled():
            return True
        heartbeat = Thread(
            target=maintain_lease,
            name=f"research-heartbeat-{job.job_id}",
            daemon=True,
        )
        heartbeat.start()
        try:
            partial = self._processor(job, cancelled)
        except RetryableJobError as error:
            outcome: tuple[str, bool | str] = (
                "fail-retryable",
                self._reason(error, "RETRYABLE_JOB_FAILURE"),
            )
        except NonRetryableJobError as error:
            outcome = ("fail-terminal", self._reason(error, "NON_RETRYABLE_JOB_FAILURE"))
        else:
            outcome = ("complete", partial)
        finally:
            heartbeat_stop.set()
            heartbeat.join()

        if cancelled():
            return True
        current_time = self._clock()
        if outcome[0] == "complete":
            self._repository.complete(
                tenant,
                job.job_id,
                claimed.lease_token,
                partial=bool(outcome[1]),
                now=current_time,
            )
        else:
            self._repository.fail(
                tenant,
                job.job_id,
                claimed.lease_token,
                str(outcome[1]),
                retryable=outcome[0] == "fail-retryable",
                now=current_time,
            )
        return True

    @staticmethod
    def _reason(error: RuntimeError, fallback: str) -> str:
        value = str(error)
        return value if value and len(value) <= 128 else fallback
