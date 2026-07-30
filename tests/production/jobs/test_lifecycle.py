import pytest

from decision_assurance.jobs.lifecycle import InvalidJobTransition, retry_delay, transition
from decision_assurance.production.contracts import JobPolicy, JobStatus


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (JobStatus.QUEUED, JobStatus.RUNNING),
        (JobStatus.RETRY_WAIT, JobStatus.RUNNING),
        (JobStatus.RUNNING, JobStatus.COMPLETED),
        (JobStatus.RUNNING, JobStatus.PARTIAL),
        (JobStatus.RUNNING, JobStatus.RETRY_WAIT),
        (JobStatus.RUNNING, JobStatus.FAILED),
        (JobStatus.RUNNING, JobStatus.DEAD_LETTER),
        (JobStatus.QUEUED, JobStatus.CANCELLED),
        (JobStatus.RUNNING, JobStatus.CANCELLED),
    ],
)
def test_allowed_job_transitions(source: JobStatus, target: JobStatus) -> None:
    assert transition(source, target) is target


def test_terminal_job_cannot_be_reopened() -> None:
    for terminal in (
        JobStatus.COMPLETED,
        JobStatus.PARTIAL,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
        JobStatus.DEAD_LETTER,
    ):
        with pytest.raises(InvalidJobTransition):
            transition(terminal, JobStatus.RUNNING)


def test_exponential_backoff_is_bounded_and_has_no_sleep() -> None:
    policy = JobPolicy(base_backoff_seconds=5, maximum_backoff_seconds=60)

    assert [retry_delay(policy, attempt) for attempt in range(1, 7)] == [5, 10, 20, 40, 60, 60]
