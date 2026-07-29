import json
from pathlib import Path

import pytest

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
