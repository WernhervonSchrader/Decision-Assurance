from dataclasses import replace
from datetime import date

from decision_assurance.identity import ActorKind, Identity, Role
from decision_assurance.intake.confirmation import confirm_fact
from decision_assurance.intake.contracts import FactType, VerificationStatus
from decision_assurance.intake.extractor import DeterministicQuoteExtractor
from decision_assurance.intake.verification import (
    InMemoryPolicyRegistry,
    IntakeVerifier,
    PolicyContext,
)
from decision_assurance.tenancy import TenantContext


def policy() -> PolicyContext:
    return PolicyContext("SALES-1", "1.0", "2026-01-01", "10", "25", 24, "50000")


def test_deterministic_facts_are_verified_but_claims_are_not_trusted() -> None:
    extraction = DeterministicQuoteExtractor().extract(
        "Quote 40,000 EUR, 8% discount, 30% margin, approved by management.",
        locale="en",
        intake_id="I-1",
    )
    report = IntakeVerifier(InMemoryPolicyRegistry({"tenant-a": policy()})).verify(
        "tenant-a", extraction
    )
    statuses = {
        candidate.fact_type: candidate.verification_status for candidate in report.candidates
    }
    assert statuses[FactType.AMOUNT] is VerificationStatus.VERIFIED
    assert statuses[FactType.DISCOUNT_PERCENT] is VerificationStatus.VERIFIED
    assert statuses[FactType.APPROVAL_CLAIM] is VerificationStatus.UNRESOLVED
    assert not report.ready
    assert "HUMAN_CONFIRMATION_REQUIRED" in report.reason_codes


def test_policy_comparison_is_derived_and_never_an_assurance_outcome() -> None:
    extraction = DeterministicQuoteExtractor().extract(
        "Quote 48,500 EUR, 12% discount and 23% margin.", locale="en", intake_id="I-2"
    )
    report = IntakeVerifier(InMemoryPolicyRegistry({"tenant-a": policy()})).verify(
        "tenant-a", extraction
    )
    assert {finding.result_code for finding in report.findings} == {
        "DISCOUNT_ABOVE_POLICY_LIMIT",
        "MARGIN_BELOW_POLICY_MINIMUM",
    }
    assert report.ready
    assert all(
        forbidden not in repr(report)
        for forbidden in ("<Outcome.PASS", "<Outcome.REVIEW", "<Outcome.BLOCK")
    )


def test_policy_registry_is_tenant_scoped_and_fails_closed() -> None:
    registry = InMemoryPolicyRegistry({"tenant-a": policy()})
    assert registry.get_active("tenant-a").policy_id == "SALES-1"
    assert registry.get_active("tenant-b") is None


def test_duration_and_policy_effective_date_are_verified() -> None:
    future_policy = replace(
        policy(), effective_date="2026-08-01", maximum_duration_months_without_exception=24
    )
    extraction = DeterministicQuoteExtractor().extract(
        "Quote 40,000 EUR, 8% discount, 30% margin, duration 36 months.",
        locale="en",
        intake_id="I-3",
    )
    report = IntakeVerifier(
        InMemoryPolicyRegistry({"tenant-a": future_policy}),
        reference_date=lambda: date(2026, 7, 29),
    ).verify("tenant-a", extraction)
    assert {finding.result_code for finding in report.findings} >= {
        "POLICY_NOT_EFFECTIVE",
        "DURATION_EXCEPTION_REQUIRED",
    }


def test_required_approval_count_and_confirmed_self_approval_are_derived() -> None:
    strict = replace(policy(), requires_approval_above_amount="0", required_approval_count=2)
    extraction = DeterministicQuoteExtractor().extract(
        "Quote 40,000 EUR, 8% discount, 30% margin. Creator performed final approval himself.",
        locale="en",
        intake_id="I-4",
    )
    candidates = tuple(
        replace(
            candidate,
            verification_status=VerificationStatus.HUMAN_CONFIRMED,
            confirmation_required=False,
        )
        if candidate.fact_type in {FactType.APPROVAL_CLAIM, FactType.SELF_APPROVAL_CLAIM}
        else candidate
        for candidate in extraction.candidates
    )
    extraction = replace(extraction, candidates=candidates)
    report = IntakeVerifier(InMemoryPolicyRegistry({"tenant-a": strict})).verify(
        "tenant-a", extraction
    )
    assert {finding.result_code for finding in report.findings} >= {
        "REQUIRED_APPROVAL_MISSING",
        "SEPARATION_OF_DUTIES_VIOLATION",
    }


def test_repeated_claims_count_only_distinct_authenticated_approvers() -> None:
    strict = replace(policy(), requires_approval_above_amount="0", required_approval_count=2)
    extraction = DeterministicQuoteExtractor().extract(
        "Quote 40,000 EUR, 8% discount, 30% margin. Sales approved. Finance approved.",
        locale="en",
        intake_id="I-5",
    )
    verifier = IntakeVerifier(InMemoryPolicyRegistry({"tenant-a": strict}))
    report = verifier.verify("tenant-a", extraction)
    approvals = [item for item in report.candidates if item.fact_type is FactType.APPROVAL_CLAIM]
    assert len(approvals) == 2
    for approval in approvals:
        report, _ = confirm_fact(
            report,
            approval.fact_id,
            action="CONFIRM",
            new_value=None,
            reason="checked",
            occurred_at="2026-07-29T10:00:00Z",
            identity=Identity(
                "approver-a", TenantContext("tenant-a"), Role.APPROVER, ActorKind.HUMAN
            ),
        )
        report = verifier.reverify("tenant-a", report)
    assert "REQUIRED_APPROVAL_MISSING" in {finding.result_code for finding in report.findings}

    report, _ = confirm_fact(
        report,
        approvals[1].fact_id,
        action="CONFIRM",
        new_value=None,
        reason="second approver checked",
        occurred_at="2026-07-29T10:01:00Z",
        identity=Identity("approver-b", TenantContext("tenant-a"), Role.APPROVER, ActorKind.HUMAN),
    )
    report = verifier.reverify("tenant-a", report)
    assert "REQUIRED_APPROVAL_MISSING" not in {finding.result_code for finding in report.findings}
