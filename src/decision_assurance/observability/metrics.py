from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from jsonschema import Draft202012Validator

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
        "mfa_denials_total",
        "tenant_conflicts_total",
        "audit_failures_total",
        "research_jobs_queued",
        "export_signature_failures_total",
        "session_store_available",
        "backup_success",
        "restore_success",
        "tls_certificate_days_remaining",
        "legal_hold_violation_attempts_total",
        "assurance_block_review_rate",
        "keycloak_available",
        "deletion_activity_total",
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
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
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

    def gauge(self, name: str, labels: Mapping[str, str] | None = None) -> float | None:
        with self._lock:
            return self._gauges.get(self._key(name, labels))

    def set_gauge(
        self, name: str, value: float, *, labels: Mapping[str, str] | None = None
    ) -> None:
        if value < 0:
            raise ValueError("INVALID_METRIC_VALUE")
        with self._lock:
            self._gauges[self._key(name, labels)] = value

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for (name, labels), counter_value in sorted(self._counters.items()):
                lines.append(f"{name}{_labels(labels)} {counter_value}")
            for (name, labels), values in sorted(self._observations.items()):
                lines.append(f"{name}_count{_labels(labels)} {len(values)}")
                lines.append(f"{name}_sum{_labels(labels)} {sum(values):.9g}")
            for (name, labels), gauge_value in sorted(self._gauges.items()):
                lines.append(f"{name}{_labels(labels)} {gauge_value:.9g}")
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


def initialize_pilot_metrics(metrics: InMemoryMetrics) -> None:
    """Publish every pilot gauge with a fail-closed baseline before the first scrape."""
    for name in (
        "backup_success",
        "restore_success",
        "tls_certificate_days_remaining",
        "session_store_available",
        "keycloak_available",
        "research_jobs_queued",
        "assurance_block_review_rate",
    ):
        metrics.set_gauge(name, 0)


class PilotOperationalEvidenceCollector:
    """Publish gauges only from measured TLS and recovery evidence."""

    def __init__(self, metrics: InMemoryMetrics):
        self._metrics = metrics

    def publish_tls(
        self,
        *,
        not_after: datetime,
        hostname_verified: bool,
        chain_verified: bool,
        now: datetime,
    ) -> bool:
        if not_after.tzinfo is None or now.tzinfo is None:
            raise ValueError("TLS_METRIC_TIME_MUST_BE_AWARE")
        seconds = (
            not_after.astimezone(timezone.utc) - now.astimezone(timezone.utc)
        ).total_seconds()
        days = max(0, int(seconds // 86_400))
        valid = hostname_verified and chain_verified and seconds > 0
        self._metrics.set_gauge("tls_certificate_days_remaining", days if valid else 0)
        return valid

    def publish_recovery(self, report: Mapping[str, object]) -> bool:
        integrity = all(
            report.get(name) is True
            for name in (
                "audit_chains_valid",
                "exports_valid",
                "tenant_isolation_valid",
                "session_decryption_valid",
                "target_met",
            )
        )
        data_bytes = report.get("data_bytes")
        digest = report.get("verification_report_sha256")
        measured = (
            report.get("schema_version") == "1.0.0"
            and isinstance(data_bytes, int)
            and not isinstance(data_bytes, bool)
            and data_bytes > 0
            and isinstance(digest, str)
            and len(digest) == 71
            and digest.startswith("sha256:")
            and all(character in "0123456789abcdef" for character in digest[7:])
            and integrity
        )
        self._metrics.set_gauge("backup_success", 1 if measured else 0)
        self._metrics.set_gauge("restore_success", 1 if measured else 0)
        return measured

    def load_files(
        self,
        *,
        tls_evidence: Path,
        recovery_evidence: Path,
        now: datetime,
    ) -> bool:
        try:
            tls = _bounded_json(tls_evidence)
            recovery = _bounded_json(recovery_evidence)
            if (
                set(tls)
                != {
                    "schema_version",
                    "not_after",
                    "hostname_verified",
                    "chain_verified",
                }
                or tls.get("schema_version") != "1.0.0"
            ):
                return False
            not_after = datetime.fromisoformat(str(tls["not_after"]).replace("Z", "+00:00"))
            recovery_schema = _bounded_json(
                Path(__file__).parents[1]
                / "schemas"
                / "production"
                / "recovery-evidence.schema.json"
            )
            if not Draft202012Validator(recovery_schema).is_valid(recovery):
                return False
            tls_valid = self.publish_tls(
                not_after=not_after,
                hostname_verified=tls.get("hostname_verified") is True,
                chain_verified=tls.get("chain_verified") is True,
                now=now,
            )
            return tls_valid and self.publish_recovery(recovery)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False


def _bounded_json(path: Path) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size > 2_000_000:
        raise ValueError("OPERATIONAL_EVIDENCE_UNAVAILABLE")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("OPERATIONAL_EVIDENCE_INVALID")
    return value


class AssuranceOutcomeCollector:
    """Derive the escalation rate from outcomes observed by this API instance."""

    def __init__(self, metrics: InMemoryMetrics):
        self._metrics = metrics
        self._review_or_block = 0
        self._total = 0
        self._lock = Lock()

    def record(self, outcome: str) -> None:
        if outcome not in {"APPROVED", "BLOCKED", "REVIEW"}:
            return
        with self._lock:
            self._total += 1
            if outcome in {"BLOCKED", "REVIEW"}:
                self._review_or_block += 1
            self._metrics.set_gauge(
                "assurance_block_review_rate", self._review_or_block / self._total
            )


def _labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    rendered = ",".join(
        f'{name}="{value.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'
        for name, value in labels
    )
    return "{" + rendered + "}"
