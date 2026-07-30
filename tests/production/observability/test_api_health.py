import json

from fastapi.testclient import TestClient

from decision_assurance.api.app import create_app
from decision_assurance.identity import StaticTokenAuthenticator
from decision_assurance.observability.health import HealthService, StaticHealthProbe
from decision_assurance.observability.logging import JsonEventLogger
from decision_assurance.observability.metrics import InMemoryMetrics
from decision_assurance.production.contracts import HealthStatus


class ReadyRepository:
    def ready(self) -> bool:
        return True


def test_health_endpoint_and_request_telemetry_share_correlation_id() -> None:
    lines: list[str] = []
    health = HealthService(
        (StaticHealthProbe("database", HealthStatus.UNAVAILABLE, "DATABASE_UNAVAILABLE"),),
        clock=lambda: "2026-07-30T10:00:00Z",
    )
    app = create_app(
        ReadyRepository(),  # type: ignore[arg-type]
        StaticTokenAuthenticator({}),
        health_service=health,
        logger=JsonEventLogger(lines.append),
        metrics=InMemoryMetrics(),
        api_version="0.5.0",
    )

    response = TestClient(app).get(
        "/health/ready", headers={"X-Correlation-ID": "correlation-health"}
    )

    assert response.status_code == 503
    assert response.json()["components"][0]["reason_code"] == "DATABASE_UNAVAILABLE"
    assert response.headers["X-Correlation-ID"] == "correlation-health"
    assert json.loads(lines[0])["correlation_id"] == "correlation-health"
