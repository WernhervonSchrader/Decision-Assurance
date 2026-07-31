from __future__ import annotations

import json

from decision_assurance.observability.logging import JsonEventLogger
from decision_assurance.production.egress import (
    EgressRequestContext,
    bind_egress_context,
)
from decision_assurance.web_research.providers.telemetry import ProviderCallTelemetry


def test_provider_telemetry_is_bounded_correlated_and_secret_free() -> None:
    lines: list[str] = []
    times = iter((10.0, 10.125))
    telemetry = ProviderCallTelemetry(JsonEventLogger(lines.append), clock=lambda: next(times))
    secret = "never-log-provider-secret"  # noqa: S105
    context = EgressRequestContext("tenant-a", "actor-a", "corr-a", lambda event: None)

    with bind_egress_context(context):
        started = telemetry.start()
        telemetry.record(
            started,
            connector="web-search-v1",
            status_code=200,
            reason_code="PROVIDER_CALL_SUCCEEDED",
        )

    event = json.loads(lines[0])
    assert set(event) == {
        "timestamp",
        "level",
        "event_type",
        "correlation_id",
        "connector",
        "status_code",
        "duration_ms",
        "reason_code",
    }
    assert event["correlation_id"] == "corr-a"
    assert event["duration_ms"] == 125.0
    assert secret not in lines[0]
