from dataclasses import replace

import pytest

from decision_assurance.identity import ActorKind, Identity, Role
from decision_assurance.intake.confirmation import ConfirmationRejected, confirm_fact
from decision_assurance.intake.contracts import PolicyContext, VerificationStatus
from decision_assurance.intake.extractor import DeterministicQuoteExtractor
from decision_assurance.intake.verification import InMemoryPolicyRegistry, IntakeVerifier
from decision_assurance.tenancy import TenantContext

POLICY = PolicyContext("P-1", "1", "2026-01-01", "10", "25", 24, "50000")


def report():  # type: ignore[no-untyped-def]
    extracted = DeterministicQuoteExtractor().extract(
        "Quote 40,000 EUR, 8% discount, 30% margin, approved by management.",
        locale="en",
        intake_id="I-1",
    )
    return IntakeVerifier(InMemoryPolicyRegistry({"a": POLICY})).verify("a", extracted)


def identity(kind: ActorKind, role: Role = Role.VALIDATOR) -> Identity:
    return Identity("actor-1", TenantContext("a"), role, kind)


def test_only_authorized_human_can_confirm_and_original_remains_immutable() -> None:
    original = report()
    fact = next(
        item
        for item in original.candidates
        if item.verification_status is VerificationStatus.UNRESOLVED
    )
    updated, confirmation = confirm_fact(
        original,
        fact.fact_id,
        action="CONFIRM",
        new_value=None,
        reason="Checked approval record",
        occurred_at="2026-07-29T10:00:00+00:00",
        identity=identity(ActorKind.HUMAN),
    )
    assert fact.verification_status is VerificationStatus.UNRESOLVED
    assert (
        next(
            item for item in updated.candidates if item.fact_id == fact.fact_id
        ).verification_status
        is VerificationStatus.HUMAN_CONFIRMED
    )
    assert confirmation.actor_id == "actor-1"


@pytest.mark.parametrize(
    "actor", [identity(ActorKind.AGENT), identity(ActorKind.HUMAN, Role.GENERATOR)]
)
def test_agent_or_unauthorized_role_cannot_confirm(actor: Identity) -> None:
    current = report()
    fact_id = next(item.fact_id for item in current.candidates if item.confirmation_required)
    with pytest.raises(ConfirmationRejected):
        confirm_fact(
            current,
            fact_id,
            action="CONFIRM",
            new_value=None,
            reason="not allowed",
            occurred_at="2026-07-29T10:00:00+00:00",
            identity=actor,
        )


def test_confirmation_is_idempotent() -> None:
    current = report()
    fact_id = next(item.fact_id for item in current.candidates if item.confirmation_required)
    updated, first = confirm_fact(
        current,
        fact_id,
        action="CONFIRM",
        new_value=None,
        reason="checked",
        occurred_at="2026-07-29T10:00:00+00:00",
        identity=identity(ActorKind.HUMAN),
    )
    replay, second = confirm_fact(
        updated,
        fact_id,
        action="CONFIRM",
        new_value=None,
        reason="checked",
        occurred_at="2026-07-29T10:00:00+00:00",
        identity=identity(ActorKind.HUMAN),
    )
    assert replace(first) == second
    assert replay == updated


def test_corrected_verified_value_requires_policy_reverification() -> None:
    extracted = DeterministicQuoteExtractor().extract(
        "Quote 40,000 EUR, 8% discount and 30% margin.", locale="en", intake_id="I-2"
    )
    current = IntakeVerifier(InMemoryPolicyRegistry({"a": POLICY})).verify("a", extracted)
    discount = next(
        item for item in current.candidates if item.fact_type.value == "DISCOUNT_PERCENT"
    )
    corrected, _ = confirm_fact(
        current,
        discount.fact_id,
        action="CORRECT",
        new_value="80",
        reason="corrected source value",
        occurred_at="2026-07-29T10:00:00+00:00",
        identity=identity(ActorKind.HUMAN),
    )
    assert not corrected.ready
    assert "REVERIFICATION_REQUIRED" in corrected.reason_codes

    reverified = IntakeVerifier(InMemoryPolicyRegistry({"a": POLICY})).reverify("a", corrected)
    assert reverified.ready
    assert {finding.result_code for finding in reverified.findings} == {
        "DISCOUNT_ABOVE_POLICY_LIMIT"
    }
