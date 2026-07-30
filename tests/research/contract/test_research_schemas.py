import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[3]
NAMES = (
    "research-request.schema.json",
    "research-run.schema.json",
    "source-candidate.schema.json",
    "source-snapshot.schema.json",
    "evidence-candidate.schema.json",
    "evidence-assessment.schema.json",
    "research-error.schema.json",
    "research-audit-event.schema.json",
)


def test_public_and_packaged_research_schemas_are_valid_and_byte_identical() -> None:
    for name in NAMES:
        public = ROOT / "schemas" / "research" / name
        packaged = ROOT / "src" / "decision_assurance" / "schemas" / "research" / name
        assert public.read_bytes() == packaged.read_bytes()
        Draft202012Validator.check_schema(json.loads(public.read_text(encoding="utf-8")))


def test_research_request_schema_rejects_identity_and_provider_fields() -> None:
    schema = json.loads(
        (ROOT / "schemas/research/research-request.schema.json").read_text(encoding="utf-8")
    )
    request = {
        "schema_version": "0.4.0",
        "decision_file_id": "D-1",
        "claim_refs": ["CLAIM-1"],
        "query": "rules",
        "locale": "en-US",
        "preferred_languages": ["en"],
        "max_search_results": 5,
        "max_sources_to_extract": 2,
        "allowed_domains": [],
        "blocked_domains": [],
        "freshness": {"maximum_age_days": 365, "prefer_recent": True},
        "research_policy": "standard",
        "force_refresh": False,
        "tenant_id": "attacker-controlled",
    }
    assert list(Draft202012Validator(schema).iter_errors(request))
