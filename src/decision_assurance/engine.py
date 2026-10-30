from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from .adapters import normalize
from .audit import AuditLedger
from .models import AssessmentResult, Finding, Outcome, Severity
from .provenance.evidence import EvidenceRegistry, evidence_binding

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DecisionAssuranceEngine:
    """Deterministic, fail-closed Decision Assurance governance engine."""

    def __init__(
        self,
        *,
        clock: Clock = _utc_now,
        engine_version: str = "0.2.0",
        evidence_registry: EvidenceRegistry | None = None,
        tenant_id: str | None = None,
        generator_id: str | None = None,
    ):
        self.clock = clock
        self.engine_version = engine_version
        # These are server composition inputs, never read from assess(payload).
        self.evidence_registry = evidence_registry
        self.tenant_id = tenant_id
        self.generator_id = generator_id

    def assess(self, payload: dict[str, Any]) -> AssessmentResult:
        data = normalize(payload)
        decision_id = str(data["decision_id"])
        ledger = AuditLedger(
            decision_id=decision_id, now=self.clock, engine_version=self.engine_version
        )
        ledger.append("decision.received", data)

        source_verifications: list[dict[str, str]] = []
        findings = self._validate(data, source_verifications)
        ledger.append(
            "evidence.validated",
            {
                "evidence": data["evidence"],
                "valid": not findings,
                "source_verifications": source_verifications,
            },
        )
        for finding in findings:
            ledger.append("finding.created", finding.as_dict())

        outcome = self._govern(findings)
        reason_codes = (
            tuple(dict.fromkeys(finding.reason_code for finding in findings))
            if findings
            else ("ALL_REQUIRED_CHECKS_SATISFIED",)
        )
        ledger.append(
            "governance.decided",
            {"outcome": outcome.value, "reason_codes": reason_codes},
        )

        review_ref = None
        if outcome is Outcome.REVIEW:
            review_ref = f"{decision_id}:review:1"
            ledger.append(
                "review.requested",
                {"review_id": review_ref, "reason_codes": reason_codes},
            )

        report_id = f"{decision_id}:report:1"
        report = {
            "report_id": report_id,
            "decision_id": decision_id,
            "outcome": outcome.value,
            "reason_codes": list(reason_codes),
            "finding_refs": [finding.finding_id for finding in findings],
            "evidence_refs": [
                str(item.get("evidence_id", item.get("id")))
                for item in data["evidence"]
                if item.get("evidence_id", item.get("id")) is not None
            ],
            "review_ref": review_ref,
            "audit_ref": f"{decision_id}:audit",
            "created_at": self.clock().isoformat(),
            "limitations": [],
            "versions": {
                "das": "0.1.0",
                "policy": str(data["policy_version"]),
                "engine": self.engine_version,
            },
        }
        return AssessmentResult(
            outcome=outcome,
            reason_codes=reason_codes,
            human_review=outcome is Outcome.REVIEW,
            findings=findings,
            report=report,
            audit_events=ledger.events,
        )

    def _source_verified(
        self,
        data: dict[str, Any],
        evidence: dict[str, Any],
        source_verifications: list[dict[str, str]],
    ) -> bool:
        if not self.evidence_registry or not self.tenant_id or not self.generator_id:
            return False
        ref = evidence.get("evidence_id", evidence.get("id"))
        source = evidence.get("source_ref")
        content_hash = evidence.get("content_hash")
        if (
            not isinstance(ref, str)
            or not ref
            or not isinstance(source, str)
            or not source.strip()
            or not isinstance(content_hash, str)
            or len(content_hash) != 71
            or not content_hash.startswith("sha256:")
            or any(c not in "0123456789abcdef" for c in content_hash[7:])
        ):
            return False
        try:
            record = self.evidence_registry.get_verified(
                self.tenant_id, str(data["decision_id"]), ref
            )
            valid = record is not None and record.matches(
                tenant_id=self.tenant_id,
                generator_id=self.generator_id,
                decision_id=str(data["decision_id"]),
                evidence_id=ref,
                binding_hash=evidence_binding(data, evidence),
                now=self.clock(),
            )
            if valid and record is not None:
                source_verifications.append(
                    {
                        "verification_id": record.verification_id,
                        "tenant_id": self.tenant_id,
                        "evidence_id": ref,
                        "validator_id": record.validator_id,
                        "binding_hash": record.binding_hash,
                    }
                )
            return valid
        except Exception:
            # Unavailable/malformed authority must never fall back to submitted trust.
            return False

    @staticmethod
    def _govern(findings: tuple[Finding, ...]) -> Outcome:
        if any(finding.severity is Severity.BLOCK for finding in findings):
            return Outcome.BLOCK
        if findings:
            return Outcome.REVIEW
        return Outcome.PASS

    def _validate(
        self,
        data: dict[str, Any],
        source_verifications: list[dict[str, str]],
    ) -> tuple[Finding, ...]:
        found: list[tuple[str, Severity, str | None]] = []
        for evidence in data["evidence"]:
            ref = evidence.get("evidence_id", evidence.get("id"))
            status = evidence.get("status")
            if not self._source_verified(data, evidence, source_verifications):
                found.append(("EVIDENCE_PROVENANCE_UNVERIFIED", Severity.REVIEW, ref))
            if status != "VERIFIED" or not evidence.get("verifiable", True):
                found.append(("EVIDENCE_UNVERIFIABLE", Severity.REVIEW, ref))
            if status == "FABRICATED" or evidence.get("fabricated", False):
                found.append(("CITATION_FABRICATED", Severity.BLOCK, ref))
            if status == "OUTDATED" or evidence.get("outdated", False):
                found.append(("EVIDENCE_OUTDATED", Severity.REVIEW, ref))
            if not evidence.get("supports_claim", True):
                found.append(("SOURCE_CLAIM_MISMATCH", Severity.REVIEW, ref))
            if status == "CONFLICTING" or evidence.get("contradicts_claim", False):
                found.append(("EVIDENCE_CONFLICT", Severity.REVIEW, ref))
            if status == "UNAVAILABLE":
                found.append(("MANDATORY_EVIDENCE_MISSING", Severity.REVIEW, ref))

        if data["mandatory_evidence_missing"]:
            missing_severity = (
                Severity.BLOCK if data["risk"].get("high_impact", False) else Severity.REVIEW
            )
            found.append(("MANDATORY_EVIDENCE_MISSING", missing_severity, None))
        for constraint in data["constraints"]:
            ref = constraint.get("constraint_id", constraint.get("id"))
            hard = constraint.get("hard", constraint.get("severity") == "MANDATORY")
            if hard and not constraint.get("satisfied", True):
                found.append(("HARD_CONSTRAINT_VIOLATION", Severity.BLOCK, ref))
            elif constraint.get("severity") == "REVIEW_REQUIRED" and not constraint.get(
                "satisfied", True
            ):
                found.append(
                    (
                        constraint.get("reason_code", "CONSTRAINT_REQUIRES_REVIEW"),
                        Severity.REVIEW,
                        ref,
                    )
                )
        for policy in data["policies"]:
            if policy.get("requires_review", False):
                found.append(
                    (
                        "POLICY_REQUIRES_REVIEW",
                        Severity.REVIEW,
                        policy.get("policy_id", policy.get("id")),
                    )
                )
        actors = data["actors"]
        if actors.get("generator") and actors.get("approver") == actors["generator"]:
            found.append(("SEPARATION_OF_DUTIES_VIOLATION", Severity.BLOCK, actors["generator"]))
        risk = data["risk"]
        if risk.get("high_impact", False) and risk.get("unresolved_uncertainty", False):
            found.append(("HIGH_IMPACT_UNCERTAINTY", Severity.REVIEW, None))
        for conflict in data["conflicts"]:
            if not conflict.get("resolved", False):
                severity = (
                    Severity.BLOCK if conflict.get("severity") == "CRITICAL" else Severity.REVIEW
                )
                code = (
                    "CRITICAL_CONFLICT_UNRESOLVED"
                    if severity is Severity.BLOCK
                    else "CONFLICT_UNRESOLVED"
                )
                found.append((code, severity, conflict.get("id")))

        return tuple(
            Finding(
                finding_id=f"{data['decision_id']}:finding:{index}",
                reason_code=reason_code,
                severity=severity,
                subject_ref=str(subject_ref) if subject_ref is not None else None,
            )
            for index, (reason_code, severity, subject_ref) in enumerate(found, start=1)
        )


def evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    """Compatibility entry point for DATS v0.1."""
    return DecisionAssuranceEngine().assess(payload).benchmark_result()
