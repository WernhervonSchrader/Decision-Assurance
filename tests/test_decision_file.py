import json
from pathlib import Path

import pytest

from decision_assurance.decision_file import DecisionFileSemanticError, evaluate_decision_file, load_decision_file, validate_semantics
from decision_assurance.validation import ContractValidationError


ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize("path", sorted((ROOT / "examples" / "decision-cases").glob("*.json")), ids=lambda p: p.stem)
def test_examples_are_valid(path: Path) -> None:
    assert load_decision_file(path)["schema_version"] == "0.1.0"


@pytest.mark.parametrize("path", sorted((ROOT / "tests" / "fixtures" / "invalid").glob("*.json")), ids=lambda p: p.stem)
def test_invalid_fixtures_are_rejected_with_context(path: Path) -> None:
    with pytest.raises(ContractValidationError) as error:
        load_decision_file(path)
    assert str(error.value)


@pytest.mark.parametrize(
    ("name", "outcome"),
    [("low-risk-pass.json", "PASS"), ("missing-evidence-review.json", "REVIEW"), ("hard-constraint-block.json", "BLOCK")],
)
def test_decision_file_evaluation(name: str, outcome: str) -> None:
    document = load_decision_file(ROOT / "examples" / "decision-cases" / name)
    updated, result = evaluate_decision_file(document)
    assert updated["decision_outcome"] == outcome
    assert result.outcome.value == outcome


def test_critical_conflict_blocks() -> None:
    document = load_decision_file(ROOT / "examples" / "decision-cases" / "low-risk-pass.json")
    document["conflicts"] = [{"id": "C-1", "severity": "CRITICAL", "resolved": False}]
    _, result = evaluate_decision_file(document)
    assert result.outcome.value == "BLOCK"
    assert "CRITICAL_CONFLICT_UNRESOLVED" in result.reason_codes


def test_unknown_claim_reference_is_rejected_semantically() -> None:
    document = load_decision_file(ROOT / "examples" / "decision-cases" / "low-risk-pass.json")
    document["evidence"][0]["claim_refs"] = ["UNKNOWN"]
    with pytest.raises(DecisionFileSemanticError, match="unknown claims"):
        validate_semantics(document)
