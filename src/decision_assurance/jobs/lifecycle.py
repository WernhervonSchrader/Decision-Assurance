from __future__ import annotations

from ..production.contracts import JobPolicy, JobStatus


class InvalidJobTransition(ValueError):
    pass


_ALLOWED: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RETRY_WAIT: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.COMPLETED,
            JobStatus.PARTIAL,
            JobStatus.RETRY_WAIT,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.DEAD_LETTER,
        }
    ),
}


def transition(source: JobStatus, target: JobStatus) -> JobStatus:
    if target not in _ALLOWED.get(source, frozenset()):
        raise InvalidJobTransition(f"INVALID_JOB_TRANSITION:{source.value}:{target.value}")
    return target


def retry_delay(policy: JobPolicy, attempt_count: int) -> int:
    if attempt_count < 1:
        raise ValueError("INVALID_JOB_ATTEMPT_COUNT")
    exponent = min(attempt_count - 1, 30)
    return min(policy.maximum_backoff_seconds, policy.base_backoff_seconds * (1 << exponent))
