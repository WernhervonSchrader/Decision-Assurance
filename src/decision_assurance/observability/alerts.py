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
        AlertRule("AuthenticationFailureBurst", "authentication_failures_total", ">", 10),
        AlertRule("MfaDenialBurst", "mfa_denials_total", ">", 5),
        AlertRule("TenantConflict", "tenant_conflicts_total", ">", 0),
        AlertRule("AuditPersistenceFailure", "audit_failures_total", ">", 0),
        AlertRule("ResearchJobBacklog", "research_jobs_queued", ">", 100),
        AlertRule("ProviderFailure", "provider_failures_total", ">", 5),
        AlertRule("ExportSignatureFailure", "export_signature_failures_total", ">", 0),
        AlertRule("SessionStoreUnavailable", "session_store_available", "<", 1),
        AlertRule("BackupFailure", "backup_success", "<", 1),
        AlertRule("RestoreFailure", "restore_success", "<", 1),
        AlertRule("CertificateExpiring", "tls_certificate_days_remaining", "<", 14),
        AlertRule("LegalHoldViolation", "legal_hold_violation_attempts_total", ">", 0),
        AlertRule("AssuranceEscalationRate", "assurance_block_review_rate", ">", 0.8),
        AlertRule("KeycloakUnavailable", "keycloak_available", "<", 1),
        AlertRule("DeletionActivityBurst", "deletion_activity_total", ">", 20),
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
