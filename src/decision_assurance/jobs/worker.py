from __future__ import annotations

from collections.abc import Callable

from ..production.contracts import JobStatus, ResearchJob
from ..tenancy import TenantContext
from .repository import JobRepository


class RetryableJobError(RuntimeError):
    pass


class NonRetryableJobError(RuntimeError):
    pass


CancellationCheck = Callable[[], bool]
ResearchProcessor = Callable[[ResearchJob, CancellationCheck], bool]


class ResearchWorker:
    def __init__(self, repository: JobRepository, processor: ResearchProcessor):
        self._repository = repository
        self._processor = processor

    def run_once(self, worker_id: str, *, now: str) -> bool:
        claimed = self._repository.claim(worker_id, now=now)
        if claimed is None:
            return False
        job = claimed.job
        tenant = TenantContext(job.tenant_id)
        if job.status is JobStatus.CANCELLED:
            return True

        def cancelled() -> bool:
            return self._repository.is_cancelled(tenant, job.job_id)

        if cancelled():
            return True
        try:
            partial = self._processor(job, cancelled)
            if cancelled():
                return True
            self._repository.complete(
                tenant,
                job.job_id,
                claimed.lease_token,
                partial=partial,
                now=now,
            )
        except RetryableJobError as error:
            self._repository.fail(
                tenant,
                job.job_id,
                claimed.lease_token,
                self._reason(error, "RETRYABLE_JOB_FAILURE"),
                retryable=True,
                now=now,
            )
        except NonRetryableJobError as error:
            self._repository.fail(
                tenant,
                job.job_id,
                claimed.lease_token,
                self._reason(error, "NON_RETRYABLE_JOB_FAILURE"),
                retryable=False,
                now=now,
            )
        return True

    @staticmethod
    def _reason(error: RuntimeError, fallback: str) -> str:
        value = str(error)
        return value if value and len(value) <= 128 else fallback
