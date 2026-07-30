from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from decision_assurance.production import GateResult, ReleaseStatus, ReleaseVerificationReport

MANDATORY_GATES = (
    "unit-quality",
    "dependency-audit",
    "secret-scan",
    "oidc-validation",
    "postgresql-migrations",
    "tenant-isolation",
    "database-roles",
    "worker-recovery",
    "production-configuration",
    "observability-health",
    "container-scan",
    "restore-verification",
    "controlled-pilot-e2e",
    "artifact-integrity",
)

BLOCKING_REASON_CODES = frozenset(
    {
        "TENANT_ISOLATION_FAILURE",
        "CRITICAL_VULNERABILITY",
        "MIGRATION_FAILURE",
        "RESTORE_FAILURE",
        "AUDIT_INTEGRITY_FAILURE",
        "STATIC_AUTH_PRODUCTION",
        "RESEARCH_OUTCOME_USED",
        "AGENT_APPROVAL",
        "SECRET_LEAKAGE",
    }
)


class ReleaseVerifier:
    """Compute release status from evidence; callers cannot assert an overall result."""

    def verify(
        self,
        *,
        version: str,
        commit_sha: str,
        generated_at: str,
        gates: Iterable[GateResult],
    ) -> ReleaseVerificationReport:
        supplied: dict[str, GateResult] = {}
        duplicate_ids: set[str] = set()
        for gate in gates:
            if gate.gate_id in supplied:
                duplicate_ids.add(gate.gate_id)
            supplied[gate.gate_id] = self._enforce_blockers(gate)

        normalized: list[GateResult] = []
        for gate_id in MANDATORY_GATES:
            if gate_id in duplicate_ids:
                normalized.append(
                    GateResult(
                        gate_id,
                        ReleaseStatus.BLOCK,
                        ("DUPLICATE_GATE_EVIDENCE",),
                        ("release-verification",),
                    )
                )
            elif gate_id not in supplied:
                normalized.append(
                    GateResult(
                        gate_id,
                        ReleaseStatus.BLOCK,
                        ("MANDATORY_GATE_MISSING",),
                        ("release-verification",),
                    )
                )
            else:
                normalized.append(supplied[gate_id])

        unknown = sorted(set(supplied).difference(MANDATORY_GATES))
        if unknown:
            normalized.append(
                GateResult(
                    "release-input",
                    ReleaseStatus.BLOCK,
                    ("UNKNOWN_RELEASE_GATE",),
                    tuple(f"gate:{gate_id}" for gate_id in unknown),
                )
            )

        return ReleaseVerificationReport(
            version=version,
            commit_sha=commit_sha,
            generated_at=generated_at,
            gates=tuple(normalized),
        )

    @staticmethod
    def _enforce_blockers(gate: GateResult) -> GateResult:
        if BLOCKING_REASON_CODES.intersection(gate.reason_codes):
            return GateResult(
                gate.gate_id,
                ReleaseStatus.BLOCK,
                gate.reason_codes,
                gate.evidence_refs,
            )
        return gate


def publication_eligible(report: ReleaseVerificationReport) -> bool:
    return (
        report.status is ReleaseStatus.PASS
        and tuple(gate.gate_id for gate in report.gates) == MANDATORY_GATES
    )


def report_to_dict(report: ReleaseVerificationReport) -> dict[str, Any]:
    return {
        "schema_version": report.schema_version,
        "version": report.version,
        "commit_sha": report.commit_sha,
        "generated_at": report.generated_at,
        "status": report.status.value,
        "gates": [
            {
                "gate_id": gate.gate_id,
                "status": gate.status.value,
                "reason_codes": list(gate.reason_codes),
                "evidence_refs": list(gate.evidence_refs),
            }
            for gate in report.gates
        ],
    }
