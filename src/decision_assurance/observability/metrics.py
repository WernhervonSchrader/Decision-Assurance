from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from threading import Lock

_ALLOWED_NAMES = frozenset(
    {
        "http_requests_total",
        "http_request_duration_seconds",
        "authentication_failures_total",
        "job_claims_total",
        "job_outcomes_total",
        "job_duration_seconds",
        "provider_requests_total",
        "provider_failures_total",
        "research_budget_rejections_total",
        "audit_anomalies_total",
        "pilot_login_total",
        "pilot_session_total",
        "pilot_lifecycle_total",
        "pilot_approval_total",
    }
)
_ALLOWED_LABELS = frozenset({"route", "status", "outcome", "provider", "reason", "retryable"})


class InMemoryMetrics:
    """Reference backend; production exporters implement the same bounded contract."""

    def __init__(self) -> None:
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)
        self._observations: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = (
            defaultdict(list)
        )
        self._lock = Lock()

    def increment(self, name: str, *, labels: Mapping[str, str] | None = None) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] += 1

    def observe(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        if value < 0:
            raise ValueError("INVALID_METRIC_VALUE")
        with self._lock:
            self._observations[self._key(name, labels)].append(value)

    def counter(self, name: str, labels: Mapping[str, str] | None = None) -> int:
        with self._lock:
            return self._counters[self._key(name, labels)]

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for (name, labels), value in sorted(self._counters.items()):
                lines.append(f"{name}{_labels(labels)} {value}")
            for (name, labels), values in sorted(self._observations.items()):
                lines.append(f"{name}_count{_labels(labels)} {len(values)}")
                lines.append(f"{name}_sum{_labels(labels)} {sum(values):.9g}")
        return "\n".join(lines) + ("\n" if lines else "")

    @staticmethod
    def _key(
        name: str, labels: Mapping[str, str] | None
    ) -> tuple[str, tuple[tuple[str, str], ...]]:
        if name not in _ALLOWED_NAMES:
            raise ValueError("METRIC_NAME_NOT_ALLOWED")
        values = labels or {}
        if set(values) - _ALLOWED_LABELS:
            raise ValueError("METRIC_LABEL_NOT_ALLOWED")
        if any(not value or len(value) > 64 for value in values.values()):
            raise ValueError("INVALID_METRIC_LABEL")
        return name, tuple(sorted(values.items()))


def _labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    rendered = ",".join(
        f'{name}="{value.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'
        for name, value in labels
    )
    return "{" + rendered + "}"
