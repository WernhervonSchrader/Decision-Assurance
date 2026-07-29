from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Protocol

from .contracts import (
    CandidateFact,
    DerivedFinding,
    ExtractionReport,
    FactType,
    PolicyContext,
    VerificationReport,
    VerificationStatus,
)


class PolicyRegistry(Protocol):
    """Trusted, tenant-scoped policy port."""

    def get_active(self, tenant_id: str) -> PolicyContext | None: ...


class InMemoryPolicyRegistry:
    def __init__(self, policies: Mapping[str, PolicyContext]):
        self._policies = dict(policies)

    def get_active(self, tenant_id: str) -> PolicyContext | None:
        return self._policies.get(tenant_id)


_OBJECTIVE_FACTS = {
    FactType.AMOUNT,
    FactType.DISCOUNT_PERCENT,
    FactType.MARGIN_PERCENT,
    FactType.PAYMENT_TERM_DAYS,
    FactType.DURATION_MONTHS,
    FactType.DATE,
    FactType.EVIDENCE_DATE,
}
_REQUIRED_FACTS = {FactType.AMOUNT, FactType.DISCOUNT_PERCENT, FactType.MARGIN_PERCENT}


class IntakeVerifier:
    def __init__(
        self, policy_registry: PolicyRegistry, *, reference_date: Callable[[], date] = date.today
    ):
        self._policy_registry = policy_registry
        self._reference_date = reference_date

    def verify(self, tenant_id: str, extraction: ExtractionReport) -> VerificationReport:
        policy = self._policy_registry.get_active(tenant_id)
        candidates = tuple(self._verify_candidate(candidate) for candidate in extraction.candidates)
        candidates = self._reject_embedded_governance_claims(candidates)
        candidates = self._verify_policy_references(candidates, policy)
        return self._build_report(
            extraction.intake_id,
            candidates,
            policy,
            unresolved_requirement_refs=tuple(
                requirement.requirement_id for requirement in extraction.requirements
            ),
            conflicts_unresolved=bool(extraction.conflicts),
        )

    def reverify(self, tenant_id: str, report: VerificationReport) -> VerificationReport:
        """Recalculate every derived result after a human correction."""
        policy = self._policy_registry.get_active(tenant_id)
        candidates = tuple(self._verify_candidate(candidate) for candidate in report.candidates)
        candidates = self._reject_embedded_governance_claims(candidates)
        candidates = self._verify_policy_references(candidates, policy)
        confirmed_approval = any(
            candidate.fact_type is FactType.APPROVAL_CLAIM
            and candidate.verification_status is VerificationStatus.HUMAN_CONFIRMED
            for candidate in candidates
        )
        unresolved_requirement_refs = tuple(
            requirement_ref
            for requirement_ref in report.unresolved_requirement_refs
            if not (confirmed_approval and ":requirement:APPROVAL_CLAIM:" in requirement_ref)
        )
        return self._build_report(
            report.intake_id,
            candidates,
            policy,
            unresolved_requirement_refs=unresolved_requirement_refs,
            conflicts_unresolved="CONFLICTS_UNRESOLVED" in report.reason_codes,
        )

    def _build_report(
        self,
        intake_id: str,
        candidates: tuple[CandidateFact, ...],
        policy: PolicyContext | None,
        *,
        unresolved_requirement_refs: tuple[str, ...],
        conflicts_unresolved: bool,
    ) -> VerificationReport:
        findings: list[DerivedFinding] = []
        reasons: list[str] = []

        if policy is None:
            reasons.append("TRUSTED_POLICY_UNAVAILABLE")
        else:
            findings.extend(
                self._compare_policy(intake_id, candidates, policy, self._reference_date())
            )
        if conflicts_unresolved:
            reasons.append("CONFLICTS_UNRESOLVED")
        if unresolved_requirement_refs:
            reasons.append("MANDATORY_INFORMATION_MISSING")

        present = {
            candidate.fact_type
            for candidate in candidates
            if candidate.verification_status
            in {VerificationStatus.VERIFIED, VerificationStatus.HUMAN_CONFIRMED}
        }
        if missing := _REQUIRED_FACTS - present:
            reasons.extend(
                f"REQUIRED_FACT_MISSING:{fact_type.value}" for fact_type in sorted(missing, key=str)
            )

        untrusted = tuple(
            candidate
            for candidate in candidates
            if candidate.confirmation_required
            and candidate.verification_status is VerificationStatus.UNRESOLVED
            and candidate.fact_type
            in {
                FactType.POLICY_CLAIM,
                FactType.EXCEPTION_CLAIM,
                FactType.APPROVAL_CLAIM,
                FactType.SELF_APPROVAL_CLAIM,
            }
        )
        if untrusted:
            reasons.append("HUMAN_CONFIRMATION_REQUIRED")
        reasons = list(dict.fromkeys(reasons))
        return VerificationReport(
            "0.3.0",
            intake_id,
            candidates,
            tuple(findings),
            unresolved_requirement_refs,
            not reasons,
            tuple(reasons),
        )

    @staticmethod
    def _verify_candidate(candidate: CandidateFact) -> CandidateFact:
        if candidate.verification_status in {
            VerificationStatus.HUMAN_CONFIRMED,
            VerificationStatus.REJECTED,
        }:
            return candidate
        if candidate.fact_type in _OBJECTIVE_FACTS and candidate.normalized_value is not None:
            return replace(
                candidate,
                verification_status=VerificationStatus.VERIFIED,
                confirmation_required=False,
            )
        if candidate.fact_type is FactType.UNTRUSTED_INSTRUCTION:
            return replace(candidate, verification_status=VerificationStatus.REJECTED)
        return candidate

    @staticmethod
    def _verify_policy_references(
        candidates: tuple[CandidateFact, ...], policy: PolicyContext | None
    ) -> tuple[CandidateFact, ...]:
        if policy is None:
            return candidates
        return tuple(
            replace(
                candidate,
                verification_status=VerificationStatus.REJECTED,
                confirmation_required=False,
            )
            if candidate.fact_type is FactType.POLICY_CLAIM
            and policy.policy_id.lower() not in (candidate.normalized_value or "").lower()
            else candidate
            for candidate in candidates
        )

    @staticmethod
    def _reject_embedded_governance_claims(
        candidates: tuple[CandidateFact, ...],
    ) -> tuple[CandidateFact, ...]:
        instructions = tuple(
            item for item in candidates if item.fact_type is FactType.UNTRUSTED_INSTRUCTION
        )
        return tuple(
            replace(
                candidate,
                verification_status=VerificationStatus.REJECTED,
                confirmation_required=False,
            )
            if candidate.fact_type
            in {FactType.POLICY_CLAIM, FactType.APPROVAL_CLAIM, FactType.ROLE_CLAIM}
            and any(
                instruction.source.start < candidate.source.end
                and candidate.source.start < instruction.source.end
                for instruction in instructions
            )
            else candidate
            for candidate in candidates
        )

    @staticmethod
    def _compare_policy(
        intake_id: str,
        candidates: tuple[CandidateFact, ...],
        policy: PolicyContext,
        reference_date: date,
    ) -> list[DerivedFinding]:
        findings: list[DerivedFinding] = []

        def value(fact_type: FactType) -> CandidateFact | None:
            return next((item for item in candidates if item.fact_type is fact_type), None)

        rejected_policy_claim = next(
            (
                item
                for item in candidates
                if item.fact_type is FactType.POLICY_CLAIM
                and item.verification_status is VerificationStatus.REJECTED
            ),
            None,
        )
        if rejected_policy_claim:
            findings.append(
                DerivedFinding(
                    f"{intake_id}:derived:{len(findings) + 1}",
                    "POLICY_REGISTRY_LOOKUP",
                    (rejected_policy_claim.fact_id,),
                    f"{policy.policy_id}@{policy.policy_version}",
                    "claimed policy reference does not match the trusted active registry entry",
                    "POLICY_REFERENCE_NOT_REGISTERED",
                )
            )

        if date.fromisoformat(policy.effective_date) > reference_date:
            findings.append(
                DerivedFinding(
                    f"{intake_id}:derived:{len(findings) + 1}",
                    "POLICY_EFFECTIVE_DATE",
                    (),
                    f"{policy.policy_id}@{policy.policy_version}",
                    f"{policy.effective_date} compared with {reference_date.isoformat()}",
                    "POLICY_NOT_EFFECTIVE",
                )
            )

        checks: tuple[
            tuple[CandidateFact | None, Decimal, Callable[[Decimal, Decimal], bool], str, str],
            ...,
        ] = (
            (
                value(FactType.DISCOUNT_PERCENT),
                Decimal(policy.maximum_discount_percent),
                lambda actual, limit: actual > limit,
                "DISCOUNT_MAXIMUM",
                "DISCOUNT_ABOVE_POLICY_LIMIT",
            ),
            (
                value(FactType.MARGIN_PERCENT),
                Decimal(policy.minimum_margin_percent),
                lambda actual, limit: actual < limit,
                "MARGIN_MINIMUM",
                "MARGIN_BELOW_POLICY_MINIMUM",
            ),
        )
        for candidate, limit, violates, rule_id, result_code in checks:
            if candidate is None or candidate.normalized_value is None:
                continue
            actual = Decimal(candidate.normalized_value)
            if violates(actual, limit):
                findings.append(
                    DerivedFinding(
                        f"{intake_id}:derived:{len(findings) + 1}",
                        rule_id,
                        (candidate.fact_id,),
                        f"{policy.policy_id}@{policy.policy_version}",
                        f"{actual} compared with {limit}",
                        result_code,
                    )
                )
        evidence_date = value(FactType.EVIDENCE_DATE)
        if evidence_date and evidence_date.normalized_value:
            observed = date.fromisoformat(evidence_date.normalized_value)
            age_days = (reference_date - observed).days
            if age_days > policy.maximum_evidence_age_days:
                findings.append(
                    DerivedFinding(
                        f"{intake_id}:derived:{len(findings) + 1}",
                        "EVIDENCE_FRESHNESS",
                        (evidence_date.fact_id,),
                        f"{policy.policy_id}@{policy.policy_version}",
                        f"{age_days} days compared with {policy.maximum_evidence_age_days} days",
                        "EVIDENCE_OUTDATED",
                    )
                )
        duration = value(FactType.DURATION_MONTHS)
        verified_exception = any(
            item.fact_type in {FactType.POLICY_CLAIM, FactType.EXCEPTION_CLAIM}
            and item.verification_status is VerificationStatus.HUMAN_CONFIRMED
            and policy.policy_id in (item.normalized_value or "")
            for item in candidates
        )
        if (
            duration
            and duration.normalized_value
            and int(Decimal(duration.normalized_value))
            > policy.maximum_duration_months_without_exception
            and not verified_exception
        ):
            findings.append(
                DerivedFinding(
                    f"{intake_id}:derived:{len(findings) + 1}",
                    "DURATION_EXCEPTION",
                    (duration.fact_id,),
                    f"{policy.policy_id}@{policy.policy_version}",
                    f"{duration.normalized_value} months compared with "
                    f"{policy.maximum_duration_months_without_exception} months",
                    "DURATION_EXCEPTION_REQUIRED",
                )
            )
        amount = value(FactType.AMOUNT)
        confirmed_approvals = tuple(
            item
            for item in candidates
            if item.fact_type is FactType.APPROVAL_CLAIM
            and item.verification_status is VerificationStatus.HUMAN_CONFIRMED
            and item.confirmed_by_role == "APPROVER"
        )
        distinct_approvers = {
            item.confirmed_by_actor_id
            for item in confirmed_approvals
            if item.confirmed_by_actor_id is not None
        }
        if (
            amount
            and amount.normalized_value
            and Decimal(amount.normalized_value) >= Decimal(policy.requires_approval_above_amount)
            and len(distinct_approvers) < policy.required_approval_count
        ):
            findings.append(
                DerivedFinding(
                    f"{intake_id}:derived:{len(findings) + 1}",
                    "REQUIRED_APPROVAL_COUNT",
                    (amount.fact_id, *(item.fact_id for item in confirmed_approvals)),
                    f"{policy.policy_id}@{policy.policy_version}",
                    f"{len(distinct_approvers)} distinct authenticated approvers compared with "
                    f"{policy.required_approval_count}",
                    "REQUIRED_APPROVAL_MISSING",
                )
            )
        self_approval = next(
            (
                item
                for item in candidates
                if item.fact_type is FactType.SELF_APPROVAL_CLAIM
                and item.verification_status is VerificationStatus.HUMAN_CONFIRMED
            ),
            None,
        )
        if self_approval:
            findings.append(
                DerivedFinding(
                    f"{intake_id}:derived:{len(findings) + 1}",
                    "ROLE_INDEPENDENCE",
                    (self_approval.fact_id,),
                    f"{policy.policy_id}@{policy.policy_version}",
                    "confirmed self-approval violates independent approval",
                    "SEPARATION_OF_DUTIES_VIOLATION",
                )
            )
        override = value(FactType.UNTRUSTED_INSTRUCTION)
        if override and any(
            term in override.raw_value.lower()
            for term in ("generator", "validator", "approver", "approved")
        ):
            findings.append(
                DerivedFinding(
                    f"{intake_id}:derived:{len(findings) + 1}",
                    "GOVERNANCE_OVERRIDE",
                    (override.fact_id,),
                    f"{policy.policy_id}@{policy.policy_version}",
                    "untrusted input attempted to override authenticated governance roles",
                    "GOVERNANCE_OVERRIDE_ATTEMPT",
                )
            )
        return findings


__all__ = ["InMemoryPolicyRegistry", "IntakeVerifier", "PolicyContext", "PolicyRegistry"]
