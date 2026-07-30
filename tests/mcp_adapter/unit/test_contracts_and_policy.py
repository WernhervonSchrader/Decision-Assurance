import pytest
from pydantic import ValidationError

from decision_assurance.mcp.contracts import (
    ResearchMode,
    ResearchResultKind,
    ResearchStartInput,
    ResearchToolResponse,
)
from decision_assurance.mcp.policy import McpResearchPolicy


def valid_start(**overrides):  # type: ignore[no-untyped-def]
    value = {
        "decision_file_id": "decision-1",
        "claim_refs": ["claim-1"],
        "query": "Welche Regeln gelten?",
        "locale": "de-DE",
        "preferred_languages": ["de", "en"],
        "mode": "VERIFIED",
        "idempotency_key": "mcp-start-1",
    }
    value.update(overrides)
    return value


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (ResearchMode.QUICK, (5, 2, ResearchResultKind.RESEARCH_ANSWER)),
        (ResearchMode.VERIFIED, (10, 5, ResearchResultKind.EVIDENCE_BUNDLE)),
        (
            ResearchMode.DEEP,
            (20, 10, ResearchResultKind.EVIDENCE_BUNDLE_WITH_CONFLICT_ANALYSIS),
        ),
    ],
)
def test_mode_caps_are_central(mode, expected) -> None:  # type: ignore[no-untyped-def]
    limits = McpResearchPolicy().effective_limits(mode, None, None)
    assert (
        limits.max_search_results,
        limits.max_sources_to_extract,
        limits.result_kind,
    ) == expected


def test_client_cannot_raise_mode_or_server_limits() -> None:
    policy = McpResearchPolicy(server_max_search_results=4, server_max_sources_to_extract=3)
    limits = policy.effective_limits(ResearchMode.DEEP, 20, 10)
    assert (limits.max_search_results, limits.max_sources_to_extract) == (4, 3)

    quick = McpResearchPolicy().effective_limits(ResearchMode.QUICK, 20, 10)
    assert (quick.max_search_results, quick.max_sources_to_extract) == (5, 2)


@pytest.mark.parametrize(
    "override",
    [
        {"decision_file_id": None},
        {"case_id": "case-1"},
        {"tenant_id": "tenant-attacker"},
        {"max_search_results": 2, "max_sources_to_extract": 3},
        {"claim_refs": ["claim-1", "claim-1"]},
    ],
)
def test_start_input_rejects_ambiguous_or_hostile_fields(override) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError):
        ResearchStartInput.model_validate(valid_start(**override))


def test_case_id_is_a_strict_alternative_to_decision_file_id() -> None:
    request = ResearchStartInput.model_validate(
        valid_start(decision_file_id=None, case_id="case-1")
    )
    assert request.target_id == "case-1"


def test_tool_response_cannot_claim_success_without_a_typed_result() -> None:
    with pytest.raises(ValidationError):
        ResearchToolResponse(ok=True, correlation_id="correlation-1")
