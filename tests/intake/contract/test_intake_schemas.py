import json
from pathlib import Path

import pytest

from decision_assurance.intake.codec import to_dict
from decision_assurance.intake.extractor import DeterministicQuoteExtractor
from decision_assurance.validation import ContractValidationError, ContractValidator

ROOT = Path(__file__).parents[3]
SCHEMA_NAMES = (
    "source-reference",
    "candidate-fact",
    "intake-request",
    "extraction-report",
    "intake-conflict",
    "verification-requirement",
    "human-confirmation",
    "compilation-report",
    "intake-audit-event",
    "intake-record",
)


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_public_and_packaged_intake_schemas_are_identical(schema_name: str) -> None:
    public = ROOT / "schemas" / "intake" / f"{schema_name}.schema.json"
    packaged = (
        ROOT / "src" / "decision_assurance" / "schemas" / "intake" / f"{schema_name}.schema.json"
    )
    assert json.loads(public.read_text(encoding="utf-8")) == json.loads(
        packaged.read_text(encoding="utf-8")
    )


def test_intake_request_contract_rejects_tenant_in_untrusted_payload() -> None:
    validator = ContractValidator(ROOT / "schemas")
    with pytest.raises(ContractValidationError):
        validator.validate(
            "intake/intake-request",
            {
                "schema_version": "0.3.0",
                "intake_id": "I-1",
                "raw_input": "quote",
                "locale": "en",
                "tenant_id": "attacker-selected",
            },
        )


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_valid_examples_and_invalid_fixtures(schema_name: str) -> None:
    validator = ContractValidator(ROOT / "schemas")
    valid = json.loads(
        (ROOT / "examples" / "intake" / "contracts" / f"{schema_name}.json").read_text(
            encoding="utf-8"
        )
    )
    invalid = json.loads(
        (ROOT / "tests" / "fixtures" / "invalid" / "intake" / f"{schema_name}.json").read_text(
            encoding="utf-8"
        )
    )
    validator.validate(f"intake/{schema_name}", valid)
    with pytest.raises(ContractValidationError):
        validator.validate(f"intake/{schema_name}", invalid)


def test_nested_candidate_contract_rejects_incomplete_source() -> None:
    validator = ContractValidator(ROOT / "schemas")
    candidate = json.loads(
        (ROOT / "examples" / "intake" / "contracts" / "candidate-fact.json").read_text(
            encoding="utf-8"
        )
    )
    candidate["source"] = {}
    with pytest.raises(ContractValidationError):
        validator.validate("intake/candidate-fact", candidate)


def test_real_extraction_report_satisfies_nested_contract() -> None:
    report = DeterministicQuoteExtractor().extract(
        "Quote 40,000 EUR, 8% discount and 30% margin.", locale="en", intake_id="I-real"
    )
    ContractValidator(ROOT / "schemas").validate("intake/extraction-report", to_dict(report))
