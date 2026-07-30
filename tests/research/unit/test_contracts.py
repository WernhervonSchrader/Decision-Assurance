from dataclasses import fields

import pytest

from decision_assurance.web_research.contracts import (
    ContentHash,
    FreshnessPolicy,
    IdempotencyKey,
    ResearchRequest,
    ResearchStatus,
)


def test_research_request_is_provider_neutral_and_has_no_trusted_identity_fields() -> None:
    request = ResearchRequest(
        decision_file_id="D-1",
        claim_refs=("claim-1",),
        query="Welche Regeln gelten?",
        locale="de-DE",
        preferred_languages=("de", "en"),
        freshness=FreshnessPolicy(365, True),
    )

    assert request.schema_version == "0.4.0"
    names = {item.name for item in fields(request)}
    assert not names & {
        "tenant_id",
        "actor_id",
        "requested_by",
        "outcome",
        "verification_status",
        "approval_status",
    }
    assert not any(name.startswith(("brave_", "firecrawl_")) for name in names)


def test_bounded_value_objects_fail_closed() -> None:
    assert ContentHash.from_text("content").value.startswith("sha256:")
    assert IdempotencyKey("request-1").value == "request-1"
    with pytest.raises(ValueError, match="INVALID_CONTENT_HASH"):
        ContentHash("sha256:bad")
    with pytest.raises(ValueError, match="INVALID_IDEMPOTENCY_KEY"):
        IdempotencyKey("")
    with pytest.raises(ValueError, match="QUERY_TOO_LONG"):
        ResearchRequest(
            decision_file_id="D-1",
            claim_refs=("claim-1",),
            query="word " * 51,
            locale="en-US",
            preferred_languages=("en",),
        )


def test_research_status_contains_no_assurance_outcomes() -> None:
    values = {item.value for item in ResearchStatus}
    assert values == {
        "CREATED",
        "SEARCHING",
        "SOURCES_DISCOVERED",
        "EXTRACTING",
        "EVIDENCE_COMPILED",
        "COMPLETED",
        "PARTIALLY_COMPLETED",
        "FAILED",
        "CANCELLED",
    }
    assert not values & {"PASS", "REVIEW", "BLOCK", "APPROVED"}
