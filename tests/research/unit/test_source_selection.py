from decision_assurance.web_research.contracts import SourceCandidate
from decision_assurance.web_research.selection import SourceSelectionPolicy


def source(source_id: str, rank: int, status: str = "DISCOVERED") -> SourceCandidate:
    return SourceCandidate(
        source_id,
        f"https://{source_id}.example/rule",
        f"https://{source_id}.example/rule",
        f"{source_id}.example",
        source_id,
        "",
        rank,
        "2026-07-29T00:00:00+00:00",
        "fake-search",
        "v1",
        status=status,
    )


def test_selection_is_ranked_bounded_and_status_scoped() -> None:
    policy = SourceSelectionPolicy()
    sources = [source("three", 3), source("failed", 1, "FAILED"), source("two", 2)]
    assert [item.source_id for item in policy.select(sources, limit=1)] == ["two"]
    assert [item.source_id for item in policy.select(sources, limit=2, statuses={"FAILED"})] == [
        "failed"
    ]
