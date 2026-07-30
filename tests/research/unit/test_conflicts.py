from dataclasses import replace

from decision_assurance.web_research.conflicts import mark_conflicting_evidence
from decision_assurance.web_research.contracts import (
    ContentRisk,
    EvidenceAssessment,
    EvidenceCandidate,
    Provenance,
    ResearchRequest,
    ResearchRun,
    ResearchStatus,
    SourceCandidate,
    SourceSnapshot,
)


def test_explicit_negation_is_marked_conservatively_without_verification() -> None:
    request = ResearchRequest("D-1", ("CLAIM-1",), "rule", "en-US", ("en",))
    run = ResearchRun(
        "run-1",
        "tenant-a",
        "actor",
        request,
        "hash",
        "fingerprint",
        ResearchStatus.EXTRACTING,
        "now",
        "now",
        "correlation",
    )
    assessment = EvidenceAssessment("CURRENT", "PRIMARY", 0.9, 0.9, "NOT_CHECKED", True, True, ())
    provenance = Provenance(1, "rule", "search", "v1", "extract", "v1", "policy")
    risk = ContentRisk()
    for index, text in enumerate(("Registration is required.", "Registration is not required."), 1):
        source_id = f"source-{index}"
        snapshot_id = f"snapshot-{index}"
        run.sources.append(
            SourceCandidate(
                source_id,
                f"https://{index}.example",
                f"https://{index}.example/",
                f"{index}.example",
                "",
                "",
                index,
                "now",
                "search",
                "v1",
                status="EXTRACTED",
            )
        )
        run.snapshots.append(
            SourceSnapshot(
                snapshot_id,
                source_id,
                f"https://{index}.example",
                f"https://{index}.example/",
                f"{index}.example",
                "",
                "now",
                "later",
                f"hash-{index}",
                200,
                "text/markdown",
                "markdown",
                text,
                "en",
                "extract",
                "v1",
                risk,
            )
        )
        run.evidence.append(
            EvidenceCandidate(
                f"evidence-{index}",
                "tenant-a",
                "run-1",
                "D-1",
                ("CLAIM-1",),
                source_id,
                snapshot_id,
                f"hash-{index}",
                replace(assessment),
                provenance,
                risk,
            )
        )

    mark_conflicting_evidence(run)

    assert {item.assessment.conflict_status for item in run.evidence} == {"CONFLICTING"}
    assert all("CONFLICTING_EVIDENCE" in item.assessment.reason_codes for item in run.evidence)
    assert {item.status for item in run.sources} == {"REVIEW_REQUIRED"}
