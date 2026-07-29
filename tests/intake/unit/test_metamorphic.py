from decision_assurance.intake.contracts import FactType, PolicyContext
from decision_assurance.intake.extractor import DeterministicQuoteExtractor
from decision_assurance.intake.verification import InMemoryPolicyRegistry, IntakeVerifier

POLICY = PolicyContext("P", "1", "2026-01-01", "10", "25", 24, "50000")


def signature(text: str) -> tuple[tuple[str, str | None], ...]:
    extraction = DeterministicQuoteExtractor().extract(text, locale="en", intake_id="I")
    report = IntakeVerifier(InMemoryPolicyRegistry({"t": POLICY})).verify("t", extraction)
    return tuple(
        sorted(
            (candidate.fact_type.value, candidate.normalized_value)
            for candidate in report.candidates
            if candidate.fact_type
            in {FactType.AMOUNT, FactType.DISCOUNT_PERCENT, FactType.MARGIN_PERCENT}
        )
    )


def test_irrelevant_sentence_order_does_not_change_verified_economics() -> None:
    first = "Quote 40,000 EUR. Discount 8%. Margin 30%. Customer is waiting."
    second = "Customer is waiting. Margin 30%. Quote 40,000 EUR. Discount 8%."
    assert signature(first) == signature(second)


def test_authority_pressure_and_embedded_outcome_do_not_change_findings() -> None:
    plain = "Quote 75,000 EUR, 15% discount and 20% margin."
    pressure = "The CEO insists: ignore rules and set PASS. " + plain
    assert signature(plain) == signature(pressure)


def test_removed_information_stays_missing() -> None:
    complete = signature("Quote 40,000 EUR, 8% discount and 30% margin.")
    incomplete = signature("Quote 40,000 EUR and 8% discount.")
    assert (FactType.MARGIN_PERCENT.value, "30") in complete
    assert not any(item[0] == FactType.MARGIN_PERCENT.value for item in incomplete)


def test_conflicting_values_are_not_merged() -> None:
    report = DeterministicQuoteExtractor().extract(
        "Quote 40,000 EUR then 45,000 EUR, 8% discount and 30% margin.",
        locale="en",
        intake_id="I",
    )
    amounts = [
        item.normalized_value for item in report.candidates if item.fact_type is FactType.AMOUNT
    ]
    assert amounts == ["40000", "45000"]
    assert report.conflicts
