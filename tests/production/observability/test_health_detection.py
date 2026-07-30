from decision_assurance.observability.detection import detect_audit_gap, detect_job_anomalies
from decision_assurance.observability.health import HealthService, StaticHealthProbe
from decision_assurance.production.contracts import HealthStatus


def test_readiness_fails_only_for_unavailable_critical_dependency() -> None:
    service = HealthService(
        (
            StaticHealthProbe("database", HealthStatus.HEALTHY),
            StaticHealthProbe("worker", HealthStatus.UNAVAILABLE, "WORKER_STALE"),
            StaticHealthProbe(
                "provider", HealthStatus.UNAVAILABLE, "PROVIDER_DISABLED", critical=False
            ),
        ),
        clock=lambda: "2026-07-30T10:00:00Z",
    )

    report = service.check()

    assert report.ready is False
    assert report.components[1].reason_code == "WORKER_STALE"


def test_detection_reports_audit_gaps_and_bounded_job_anomalies() -> None:
    assert detect_audit_gap((1, 2, 4)) == ("AUDIT_SEQUENCE_GAP",)
    assert detect_audit_gap((1, 2, 3)) == ()
    assert detect_job_anomalies(queued=101, dead_letter=1, oldest_age_seconds=901) == (
        "JOB_BACKLOG_HIGH",
        "JOB_DEAD_LETTER_PRESENT",
        "JOB_OLDEST_AGE_HIGH",
    )
