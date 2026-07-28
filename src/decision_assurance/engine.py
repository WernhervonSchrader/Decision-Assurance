from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from .adapters import normalize
from .audit import AuditLedger
from .models import AssessmentResult, Finding, Outcome, Severity


Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DecisionAssuranceEngine:
    """Deterministic, fail-closed Decision Assurance governance engine."""

    def __init__(self, *, clock: Clock = _utc_now, engine_version: str = "0.1.0"):
        self.clock = clock
        self.engine_version = engine_version

    def assess(self, payload: dict[str, Any]) -> AssessmentResult:
        data = normalize(payload)
        decision_id = str(data["decision_id"])
        ledger = AuditLedger(decision_id=decision_id, now=self.clock)
        ledger.append("decision.received", data)

        findings = self._validate(data)
        ledger.append(
            "evidence.validated", {"evidence": data["evidence"], "valid": not findings}
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

    @staticmethod
    def _govern(findings: tuple[Finding, ...]) -> Outcome:
        if any(finding.severity is Severity.BLOCK for finding in findings):
            return Outcome.BLOCK
        if findings:
            return Outcome.REVIEW
        return Outcome.PASS

    @staticmethod
    def _validate(data: dict[str, Any]) -> tuple[Finding, ...]:
        found: list[tuple[str, Severity, str | None]] = []
        for evidence in data["evidence"]:
            ref = evidence.get("evidence_id", evidence.get("id"))
            status = evidence.get("status")
            if not evidence.get("verifiable", status != "UNVERIFIED"):
                found.append(("EVIDENCE_UNVERIFIABLE", Severity.REVIEW, ref))
            if evidence.get("fabricated", False):
                found.append(("CITATION_FABRICATED", Severity.BLOCK, ref))
            if evidence.get("outdated", status == "OUTDATED"):
                found.append(("EVIDENCE_OUTDATED", Severity.REVIEW, ref))
            if not evidence.get("supports_claim", True):
                found.append(("SOURCE_CLAIM_MISMATCH", Severity.REVIEW, ref))
            if evidence.get("contradicts_claim", status == "CONFLICTING"):
                found.append(("EVIDENCE_CONFLICT", Severity.REVIEW, ref))
            if status == "UNAVAILABLE":
                found.append(("MANDATORY_EVIDENCE_MISSING", Severity.REVIEW, ref))

        if data["mandatory_evidence_missing"]:
            found.append(("MANDATORY_EVIDENCE_MISSING", Severity.REVIEW, None))
        for constraint in data["constraints"]:
            ref = constraint.get("constraint_id", constraint.get("id"))
            hard = constraint.get("hard", constraint.get("severity") == "MANDATORY")
            if hard and not constraint.get("satisfied", True):
                found.append(("HARD_CONSTRAINT_VIOLATION", Severity.BLOCK, ref))
            elif constraint.get("severity") == "REVIEW_REQUIRED" and not constraint.get(
                "satisfied", True
            ):
                found.append(
                    (constraint.get("reason_code", "CONSTRAINT_REQUIRES_REVIEW"), Severity.REVIEW, ref)
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
