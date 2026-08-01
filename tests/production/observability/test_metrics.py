import pytest

from decision_assurance.observability.metrics import InMemoryMetrics


def test_metrics_accept_only_bounded_names_and_labels() -> None:
    metrics = InMemoryMetrics()
    metrics.increment("http_requests_total", labels={"route": "research-create", "status": "2xx"})
    metrics.observe("job_duration_seconds", 0.25, labels={"outcome": "completed"})

    assert (
        metrics.counter("http_requests_total", {"route": "research-create", "status": "2xx"}) == 1
    )
    metrics.increment("pilot_login_total", labels={"status": "success"})
    metrics.increment("pilot_approval_total", labels={"status": "approved"})
    assert metrics.counter("pilot_login_total", {"status": "success"}) == 1
    with pytest.raises(ValueError, match="METRIC_LABEL_NOT_ALLOWED"):
        metrics.increment("http_requests_total", labels={"tenant_id": "tenant-a"})
    with pytest.raises(ValueError, match="METRIC_NAME_NOT_ALLOWED"):
        metrics.increment("customer_specific_metric")
