import json

import pytest

from decision_assurance.observability.logging import JsonEventLogger


def test_json_logger_allows_operational_fields_and_redacts_sensitive_content() -> None:
    lines: list[str] = []
    canary = "postgresql://user:canary-password@database/tenant"
    logger = JsonEventLogger(lines.append)

    logger.emit(
        "request.completed",
        level="INFO",
        correlation_id="correlation-1",
        fields={
            "method": "POST",
            "status_code": 202,
            "authorization": "Bearer canary-token",
            "error": canary,
        },
    )

    event = json.loads(lines[0])
    assert event["correlation_id"] == "correlation-1"
    assert event["authorization"] == "**redacted**"
    assert canary not in lines[0]
    assert "canary-token" not in lines[0]


def test_unknown_log_fields_are_rejected() -> None:
    logger = JsonEventLogger(lambda value: None)
    with pytest.raises(ValueError, match="LOG_FIELD_NOT_ALLOWED"):
        logger.emit(
            "request.completed",
            level="INFO",
            correlation_id="correlation-1",
            fields={"unbounded_customer_value": "no"},
        )
