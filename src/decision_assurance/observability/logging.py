from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime, timezone

_ALLOWED_FIELDS = frozenset(
    {
        "method",
        "route",
        "status_code",
        "duration_ms",
        "job_id",
        "research_run_id",
        "event_id",
        "outcome",
        "reason_code",
        "retryable",
        "attempt_count",
        "provider_id",
        "connector",
        "schema_version",
        "security_event_type",
        "decision",
        "actor_ref",
        "tenant_id",
        "client_id",
        "permission",
        "authorization",
        "error",
    }
)
_SENSITIVE_FIELDS = frozenset({"authorization", "error"})
_SENSITIVE_VALUE = re.compile(
    r"(?i)(?:bearer\s+\S+|postgres(?:ql)?://\S+|(?:api[_-]?key|token|password|secret)[=:]\S+)"
)


class JsonEventLogger:
    def __init__(self, sink: Callable[[str], None]):
        self._sink = sink

    def emit(
        self,
        event_type: str,
        *,
        level: str,
        correlation_id: str,
        fields: Mapping[str, str | int | float | bool | None],
    ) -> None:
        if not event_type or level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("INVALID_LOG_EVENT")
        if not correlation_id or len(correlation_id) > 256:
            raise ValueError("INVALID_CORRELATION_ID")
        unknown = set(fields) - _ALLOWED_FIELDS
        if unknown:
            raise ValueError("LOG_FIELD_NOT_ALLOWED")
        event: dict[str, str | int | float | bool | None] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event_type": event_type,
            "correlation_id": correlation_id,
        }
        for key, value in fields.items():
            event[key] = self._redact(key, value)
        self._sink(json.dumps(event, sort_keys=True, separators=(",", ":")))

    @staticmethod
    def _redact(
        key: str, value: str | int | float | bool | None
    ) -> str | int | float | bool | None:
        if key in _SENSITIVE_FIELDS:
            return "**redacted**"
        if isinstance(value, str) and _SENSITIVE_VALUE.search(value):
            return "**redacted**"
        return value
