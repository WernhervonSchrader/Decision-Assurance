from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

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

    def increment(self, name: str, *, labels: Mapping[str, str] | None = None) -> None:
        key = self._key(name, labels)
        self._counters[key] += 1

    def observe(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        if value < 0:
            raise ValueError("INVALID_METRIC_VALUE")
        self._observations[self._key(name, labels)].append(value)

    def counter(self, name: str, labels: Mapping[str, str] | None = None) -> int:
        return self._counters[self._key(name, labels)]

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
