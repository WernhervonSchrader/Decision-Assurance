from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AlertRule:
    name: str
    metric: str
    operator: str
    threshold: float
    labels: frozenset[str] = frozenset({"severity"})


def default_alert_rules() -> tuple[AlertRule, ...]:
    return (
        AlertRule("AuthenticationFailureBurst", "da_auth_failures_total", ">", 10),
        AlertRule("MfaDenialBurst", "da_mfa_denials_total", ">", 5),
        AlertRule("TenantConflict", "da_tenant_conflicts_total", ">", 0),
        AlertRule("AuditPersistenceFailure", "da_audit_failures_total", ">", 0),
        AlertRule("ResearchJobBacklog", "da_research_jobs_queued", ">", 100),
        AlertRule("ProviderFailure", "da_provider_failures_total", ">", 5),
        AlertRule("ExportSignatureFailure", "da_export_signature_failures_total", ">", 0),
        AlertRule("SessionStoreUnavailable", "da_session_store_available", "<", 1),
        AlertRule("BackupFailure", "da_backup_success", "<", 1),
        AlertRule("RestoreFailure", "da_restore_success", "<", 1),
        AlertRule("CertificateExpiring", "da_tls_certificate_days_remaining", "<", 14),
        AlertRule("LegalHoldViolation", "da_legal_hold_violation_attempts_total", ">", 0),
    )


class AlertEvaluator:
    def __init__(self, rules: tuple[AlertRule, ...]):
        self._rules = rules

    def evaluate(self, metrics: Mapping[str, float]) -> tuple[str, ...]:
        firing: list[str] = []
        for rule in self._rules:
            value = metrics.get(rule.metric)
            if value is None:
                continue
            matched = value > rule.threshold if rule.operator == ">" else value < rule.threshold
            if matched:
                firing.append(rule.name)
        return tuple(firing)
