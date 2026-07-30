import pytest

from decision_assurance.web_research.contracts import ResearchStatus
from decision_assurance.web_research.lifecycle import ResearchTransitionRejected, transition


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (ResearchStatus.CREATED, ResearchStatus.SEARCHING),
        (ResearchStatus.SEARCHING, ResearchStatus.SOURCES_DISCOVERED),
        (ResearchStatus.SOURCES_DISCOVERED, ResearchStatus.EXTRACTING),
        (ResearchStatus.EXTRACTING, ResearchStatus.EVIDENCE_COMPILED),
        (ResearchStatus.EVIDENCE_COMPILED, ResearchStatus.COMPLETED),
        (ResearchStatus.EXTRACTING, ResearchStatus.PARTIALLY_COMPLETED),
        (ResearchStatus.SEARCHING, ResearchStatus.FAILED),
        (ResearchStatus.EXTRACTING, ResearchStatus.CANCELLED),
    ],
)
def test_allowed_transitions(source: ResearchStatus, target: ResearchStatus) -> None:
    assert transition(source, target) is target


def test_terminal_and_retry_transitions_are_explicit() -> None:
    with pytest.raises(ResearchTransitionRejected, match="RESEARCH_TRANSITION_NOT_ALLOWED"):
        transition(ResearchStatus.COMPLETED, ResearchStatus.SEARCHING)
    with pytest.raises(ResearchTransitionRejected, match="RETRY_REQUIRED"):
        transition(ResearchStatus.FAILED, ResearchStatus.SEARCHING)
    assert (
        transition(ResearchStatus.FAILED, ResearchStatus.SEARCHING, retry=True)
        is ResearchStatus.SEARCHING
    )
    assert (
        transition(ResearchStatus.PARTIALLY_COMPLETED, ResearchStatus.EXTRACTING, retry=True)
        is ResearchStatus.EXTRACTING
    )
