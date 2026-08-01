from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RecoveryEvidence:
    schema_version: str
    environment: str
    commit_sha: str
    data_bytes: int
    backup_started: datetime
    backup_completed: datetime
    failure_at: datetime
    restore_started: datetime
    restore_completed: datetime
    latest_restored_record_at: datetime
    audit_chains_valid: bool
    exports_valid: bool
    tenant_isolation_valid: bool
    target_rpo_seconds: int
    target_rto_seconds: int

    def report(self) -> dict[str, object]:
        ordered = (
            self.backup_started
            <= self.backup_completed
            <= self.failure_at
            <= self.restore_started
            <= self.restore_completed
        )
        if (
            self.schema_version != "1.0.0"
            or not self.environment
            or len(self.commit_sha) not in {40, 64}
            or self.data_bytes <= 0
            or not ordered
            or self.latest_restored_record_at > self.failure_at
            or min(self.target_rpo_seconds, self.target_rto_seconds) < 0
        ):
            raise ValueError("INVALID_RECOVERY_EVIDENCE")
        if not (self.audit_chains_valid and self.exports_valid and self.tenant_isolation_valid):
            raise ValueError("RECOVERY_INTEGRITY_FAILED")
        observed_rpo = int((self.failure_at - self.latest_restored_record_at).total_seconds())
        observed_rto = int((self.restore_completed - self.failure_at).total_seconds())
        return {
            "schema_version": self.schema_version,
            "environment": self.environment,
            "commit_sha": self.commit_sha,
            "data_bytes": self.data_bytes,
            "target_rpo_seconds": self.target_rpo_seconds,
            "observed_rpo_seconds": observed_rpo,
            "target_rto_seconds": self.target_rto_seconds,
            "observed_rto_seconds": observed_rto,
            "target_met": observed_rpo <= self.target_rpo_seconds
            and observed_rto <= self.target_rto_seconds,
            "scope": "TEST_OBSERVATION_NOT_SERVICE_COMMITMENT",
        }
