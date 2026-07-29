import json
from dataclasses import replace
from datetime import date
from pathlib import Path

from decision_assurance.decision_file import evaluate_decision_file
from decision_assurance.intake.codec import policy_from_dict
from decision_assurance.intake.compiler import DecisionFileCompiler
from decision_assurance.intake.contracts import FactType, VerificationStatus
from decision_assurance.intake.extractor import DeterministicQuoteExtractor
from decision_assurance.intake.verification import InMemoryPolicyRegistry, IntakeVerifier

CASES = Path(__file__).parents[3] / "benchmarks" / "intake" / "cases"


def load(path: Path):  # type: ignore[no-untyped-def]
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_13_cases_have_complete_separated_fixtures() -> None:
    cases = sorted(path for path in CASES.iterdir() if path.is_dir())
    assert len(cases) == 13
    for case in cases:
        assert {item.name for item in case.iterdir()} == {
            "raw_input.txt",
            "request.json",
            "trusted_context.json",
            "expected.json",
        }


def test_intake_benchmark_raw_and_trusted_variants() -> None:
    for case in sorted(path for path in CASES.iterdir() if path.is_dir()):
        request = load(case / "request.json")
        context = load(case / "trusted_context.json")
        expected = load(case / "expected.json")
        extraction = DeterministicQuoteExtractor().extract(
            (case / "raw_input.txt").read_text(encoding="utf-8"),
            locale=request["locale"],
            intake_id=request["intake_id"],
        )
        extracted_types = {candidate.fact_type.value for candidate in extraction.candidates}
        assert set(expected["candidate_types"]) <= extracted_types, case.name

        raw = IntakeVerifier(InMemoryPolicyRegistry({})).verify("benchmark", extraction)
        assert ("READY" if raw.ready else "NEEDS_CONFIRMATION") == expected["raw_only_status"]

        policy_data = context.get("policy")
        registry = (
            InMemoryPolicyRegistry({"benchmark": policy_from_dict(policy_data)})
            if policy_data
            else InMemoryPolicyRegistry({})
        )
        reference_date = date.fromisoformat(context.get("reference_date", "2026-07-29"))
        trusted = IntakeVerifier(
            registry, reference_date=lambda value=reference_date: value
        ).verify("benchmark", extraction)
        confirmed = set(context.get("confirmed_fact_types", []))
        if confirmed:
            candidates = tuple(
                replace(
                    candidate,
                    verification_status=VerificationStatus.HUMAN_CONFIRMED,
                    confirmation_required=False,
                )
                if candidate.fact_type.value in confirmed
                else candidate
                for candidate in trusted.candidates
            )
            blocking_claim = any(
                item.confirmation_required
                and item.fact_type
                in {FactType.POLICY_CLAIM, FactType.EXCEPTION_CLAIM, FactType.APPROVAL_CLAIM}
                for item in candidates
            )
            reasons = tuple(
                code
                for code in trusted.reason_codes
                if code != "HUMAN_CONFIRMATION_REQUIRED" or blocking_claim
            )
            trusted = replace(
                trusted, candidates=candidates, reason_codes=reasons, ready=not reasons
            )
        status = "READY" if trusted.ready else "NEEDS_CONFIRMATION"
        assert status == expected["trusted_status"], case.name
        if expected["trusted_outcome"] is not None:
            decision = DecisionFileCompiler().compile(
                trusted, policy=policy_from_dict(policy_data), actor_id="system:intake-compiler"
            )
            _, result = evaluate_decision_file(decision)
            assert result.outcome.value == expected["trusted_outcome"], case.name
