from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
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
}
_REQUIRED_FACTS = {FactType.AMOUNT, FactType.DISCOUNT_PERCENT, FactType.MARGIN_PERCENT}


class IntakeVerifier:
    def __init__(self, policy_registry: PolicyRegistry):
        self._policy_registry = policy_registry

    def verify(self, tenant_id: str, extraction: ExtractionReport) -> VerificationReport:
        policy = self._policy_registry.get_active(tenant_id)
        candidates = tuple(self._verify_candidate(candidate) for candidate in extraction.candidates)
        findings: list[DerivedFinding] = []
        reasons: list[str] = []

        if policy is None:
            reasons.append("TRUSTED_POLICY_UNAVAILABLE")
        else:
            findings.extend(self._compare_policy(extraction.intake_id, candidates, policy))
        if extraction.conflicts:
            reasons.append("CONFLICTS_UNRESOLVED")
        if extraction.requirements:
            reasons.append("MANDATORY_INFORMATION_MISSING")

        present = {
            candidate.fact_type
            for candidate in candidates
            if candidate.verification_status is VerificationStatus.VERIFIED
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
            and candidate.fact_type is not FactType.UNTRUSTED_INSTRUCTION
        )
        if untrusted or findings:
            reasons.append("HUMAN_CONFIRMATION_REQUIRED")
        reasons = list(dict.fromkeys(reasons))
        return VerificationReport(
            "0.3.0",
            extraction.intake_id,
            candidates,
            tuple(findings),
            tuple(requirement.requirement_id for requirement in extraction.requirements),
            not reasons,
            tuple(reasons),
        )

    @staticmethod
    def _verify_candidate(candidate: CandidateFact) -> CandidateFact:
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
    def _compare_policy(
        intake_id: str,
        candidates: tuple[CandidateFact, ...],
        policy: PolicyContext,
    ) -> list[DerivedFinding]:
        findings: list[DerivedFinding] = []

        def value(fact_type: FactType) -> CandidateFact | None:
            return next((item for item in candidates if item.fact_type is fact_type), None)

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
        return findings


__all__ = ["InMemoryPolicyRegistry", "IntakeVerifier", "PolicyContext", "PolicyRegistry"]
