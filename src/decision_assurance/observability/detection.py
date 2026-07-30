from __future__ import annotations


def detect_audit_gap(sequences: tuple[int, ...]) -> tuple[str, ...]:
    if not sequences:
        return ()
    expected = tuple(range(sequences[0], sequences[0] + len(sequences)))
    return () if sequences == expected else ("AUDIT_SEQUENCE_GAP",)


def detect_job_anomalies(
    *, queued: int, dead_letter: int, oldest_age_seconds: int
) -> tuple[str, ...]:
    reasons: list[str] = []
    if queued > 100:
        reasons.append("JOB_BACKLOG_HIGH")
    if dead_letter > 0:
        reasons.append("JOB_DEAD_LETTER_PRESENT")
    if oldest_age_seconds > 900:
        reasons.append("JOB_OLDEST_AGE_HIGH")
    return tuple(reasons)
