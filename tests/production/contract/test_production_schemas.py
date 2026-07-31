import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).parents[3]
PUBLIC = ROOT / "schemas" / "production"
PACKAGED = ROOT / "src" / "decision_assurance" / "schemas" / "production"


def schema(name: str) -> dict:  # type: ignore[type-arg]
    value = json.loads((PUBLIC / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(value)
    return value


def test_public_and_packaged_production_schemas_are_byte_identical() -> None:
    names = sorted(item.name for item in PUBLIC.glob("*.schema.json"))
    assert names == [
        "health-report.schema.json",
        "pilot-profile.schema.json",
        "release-verification.schema.json",
        "research-job.schema.json",
    ]
    for name in names:
        assert (PUBLIC / name).read_bytes() == (PACKAGED / name).read_bytes()


def test_job_contract_contains_no_assurance_outcome_state() -> None:
    statuses = set(schema("research-job.schema.json")["properties"]["status"]["enum"])
    assert not statuses & {"PASS", "REVIEW", "BLOCK", "APPROVED"}


def test_pilot_contract_requires_human_approval_and_rejects_unknown_fields() -> None:
    value = {
        "schema_version": "0.5.0",
        "profile_id": "sales-quote-pilot",
        "use_case": "Sales Quote Review",
        "maximum_users": 25,
        "maximum_tenants": 2,
        "maximum_research_budget": 100,
        "maximum_research_concurrency": 2,
        "supported_locales": ["de", "en"],
        "supported_providers": ["openai-web-search", "firecrawl"],
        "allowed_data_classes": ["business-confidential"],
        "retention_days": 90,
        "feature_flags": ["background-research"],
        "escalation_process": "Escalate to pilot owner.",
        "stop_criteria": ["tenant-isolation-failure"],
        "human_approval_required": True,
    }
    validator = Draft202012Validator(schema("pilot-profile.schema.json"))
    validator.validate(value)
    with pytest.raises(ValidationError):
        validator.validate({**value, "human_approval_required": False})
    with pytest.raises(ValidationError):
        validator.validate({**value, "tenant_id": "client-controlled"})
