import json
from pathlib import Path

from jsonschema import Draft202012Validator

from decision_assurance.mcp.contracts import ResearchStartInput
from decision_assurance.mcp.service import McpApplicationError, McpResearchService

ROOT = Path(__file__).parents[3]


def _schemas() -> list[str]:
    return ["research-start-input.schema.json", "research-tool-response.schema.json"]


def test_public_and_packaged_mcp_schemas_are_valid_and_identical() -> None:
    for name in _schemas():
        public = ROOT / "schemas" / "mcp" / name
        packaged = ROOT / "src" / "decision_assurance" / "schemas" / "mcp" / name
        assert public.read_bytes() == packaged.read_bytes()
        Draft202012Validator.check_schema(json.loads(public.read_text(encoding="utf-8")))


def test_contract_instances_validate_against_public_schemas() -> None:
    start = ResearchStartInput(
        decision_file_id="decision-1",
        claim_refs=["claim-1"],
        query="Current requirements",
        locale="en-US",
        preferred_languages=["en"],
        mode="VERIFIED",
        idempotency_key="start-1",
    )
    start_schema = json.loads(
        (ROOT / "schemas" / "mcp" / "research-start-input.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(start_schema).validate(start.model_dump(mode="json"))

    error = McpResearchService.error_response(McpApplicationError("FORBIDDEN"), "de")
    response_schema = json.loads(
        (ROOT / "schemas" / "mcp" / "research-tool-response.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(response_schema).validate(error.model_dump(mode="json"))


def test_schemas_expose_no_tenant_or_assurance_outcome_input() -> None:
    serialized = " ".join(
        (ROOT / "schemas" / "mcp" / name).read_text(encoding="utf-8") for name in _schemas()
    )
    assert "tenant_id" not in serialized
    assert "decision_outcome" not in serialized
