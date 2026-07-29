from __future__ import annotations

from .contracts import ResearchStatus


class ResearchTransitionRejected(ValueError):
    pass


_ALLOWED = {
    (ResearchStatus.CREATED, ResearchStatus.SEARCHING),
    (ResearchStatus.SEARCHING, ResearchStatus.SOURCES_DISCOVERED),
    (ResearchStatus.SOURCES_DISCOVERED, ResearchStatus.EXTRACTING),
    (ResearchStatus.EXTRACTING, ResearchStatus.EVIDENCE_COMPILED),
    (ResearchStatus.EVIDENCE_COMPILED, ResearchStatus.COMPLETED),
    (ResearchStatus.SEARCHING, ResearchStatus.FAILED),
    (ResearchStatus.SOURCES_DISCOVERED, ResearchStatus.FAILED),
    (ResearchStatus.EXTRACTING, ResearchStatus.FAILED),
    (ResearchStatus.EVIDENCE_COMPILED, ResearchStatus.FAILED),
    (ResearchStatus.EXTRACTING, ResearchStatus.PARTIALLY_COMPLETED),
    (ResearchStatus.EVIDENCE_COMPILED, ResearchStatus.PARTIALLY_COMPLETED),
}
_RETRY = {
    (ResearchStatus.FAILED, ResearchStatus.SEARCHING),
    (ResearchStatus.FAILED, ResearchStatus.EXTRACTING),
    (ResearchStatus.PARTIALLY_COMPLETED, ResearchStatus.EXTRACTING),
}
_CANCELLABLE = {
    ResearchStatus.CREATED,
    ResearchStatus.SEARCHING,
    ResearchStatus.SOURCES_DISCOVERED,
    ResearchStatus.EXTRACTING,
    ResearchStatus.EVIDENCE_COMPILED,
    ResearchStatus.FAILED,
    ResearchStatus.PARTIALLY_COMPLETED,
}


def transition(
    source: ResearchStatus, target: ResearchStatus, *, retry: bool = False
) -> ResearchStatus:
    if target is ResearchStatus.CANCELLED and source in _CANCELLABLE:
        return target
    if (source, target) in _RETRY:
        if not retry:
            raise ResearchTransitionRejected("RETRY_REQUIRED")
        return target
    if (source, target) not in _ALLOWED:
        raise ResearchTransitionRejected("RESEARCH_TRANSITION_NOT_ALLOWED")
    return target
