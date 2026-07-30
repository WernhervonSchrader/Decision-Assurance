import copy
from pathlib import Path

import pytest

from decision_assurance.audit import payload_hash
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.tenancy import TenantContext
from decision_assurance.web_research.compiler import (
    DecisionEvidenceHandoffRejected,
    SqliteDecisionEvidenceHandoff,
)
from decision_assurance.web_research.contracts import (
    DecisionEvidence,
    ResearchRequest,
    ResearchRun,
    ResearchStatus,
)
from decision_assurance.web_research.repository import SqliteResearchRepository


def example() -> dict:  # type: ignore[type-arg]
    return copy.deepcopy(
        __import__("json").loads(Path("examples/decision-cases/low-risk-pass.json").read_text())
    )


def evidence() -> tuple[DecisionEvidence, ...]:
    return (
        DecisionEvidence(
            evidence_id="research-evidence-1",
            research_run_id="run-1",
            claim_refs=("CLAIM-1",),
            source_ref="research:run-1:evidence-1",
            status="UNVERIFIED",
            observed_at="2026-07-29T00:00:00+00:00",
            content_hash="sha256:" + "a" * 64,
        ),
    )


def setup(tmp_path) -> tuple[SqliteDecisionRepository, SqliteDecisionEvidenceHandoff]:  # type: ignore[no-untyped-def]
    database = tmp_path / "handoff.db"
    decisions = SqliteDecisionRepository(database)
    research = SqliteResearchRepository(database)
    decisions.initialize()
    research.initialize()
    research.create_or_get(
        TenantContext("tenant-a"),
        ResearchRun(
            research_run_id="run-1",
            tenant_id="tenant-a",
            actor_id="researcher",
            request=ResearchRequest(
                decision_file_id="EXAMPLE-LOW-RISK-001",
                claim_refs=("CLAIM-1",),
                query="approved price list",
                locale="en-US",
                preferred_languages=("en",),
            ),
            expected_document_hash="sha256:" + "0" * 64,
            semantic_fingerprint="sha256:" + "1" * 64,
            status=ResearchStatus.CREATED,
            created_at="2026-07-29T00:00:00+00:00",
            updated_at="2026-07-29T00:00:00+00:00",
            correlation_id="correlation-1",
        ),
    )
    return decisions, SqliteDecisionEvidenceHandoff(database)


def test_handoff_is_draft_claim_and_cas_bound_and_never_verifies(tmp_path) -> None:  # type: ignore[no-untyped-def]
    decisions, handoff = setup(tmp_path)
    tenant = TenantContext("tenant-a")
    document = example()
    decisions.create_decision(tenant, document)
    expected = payload_hash(document)

    updated = handoff.attach(tenant, document["decision_id"], expected, evidence())
    attached = next(item for item in updated["evidence"] if item["id"] == "research-evidence-1")
    assert attached["status"] == "UNVERIFIED"
    assert updated["status"] == "DRAFT"
    assert updated["decision_outcome"] is None

    assert handoff.attach(tenant, document["decision_id"], expected, evidence()) == updated
    assert len([item for item in updated["evidence"] if item["id"] == "research-evidence-1"]) == 1

    with pytest.raises(DecisionEvidenceHandoffRejected, match="DECISION_DOCUMENT_CHANGED"):
        different_evidence = (
            DecisionEvidence(
                evidence_id="research-evidence-2",
                research_run_id="run-1",
                claim_refs=("CLAIM-1",),
                source_ref="research:run-1:evidence-2",
                status="UNVERIFIED",
                observed_at="2026-07-29T00:00:00+00:00",
                content_hash="sha256:" + "b" * 64,
            ),
        )
        handoff.attach(
            tenant,
            document["decision_id"],
            "sha256:" + "b" * 64,
            different_evidence,
        )


def test_cross_tenant_non_draft_and_unknown_claim_fail_closed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    decisions, handoff = setup(tmp_path)
    tenant = TenantContext("tenant-a")
    document = example()
    decisions.create_decision(tenant, document)

    with pytest.raises(DecisionEvidenceHandoffRejected, match="DECISION_NOT_FOUND"):
        handoff.attach(
            TenantContext("tenant-b"), document["decision_id"], payload_hash(document), evidence()
        )

    invalid = (copy.copy(evidence()[0]),)
    object.__setattr__(invalid[0], "claim_refs", ("missing-claim",))
    with pytest.raises(DecisionEvidenceHandoffRejected, match="CLAIM_REFERENCE_NOT_FOUND"):
        handoff.attach(tenant, document["decision_id"], payload_hash(document), invalid)

    document["status"] = "VALIDATION"
    decisions.save_result(tenant, document, None, [])
    with pytest.raises(DecisionEvidenceHandoffRejected, match="DECISION_NOT_DRAFT"):
        handoff.attach(tenant, document["decision_id"], payload_hash(document), evidence())
