from __future__ import annotations

from dataclasses import dataclass

from .contracts import ResearchMode, ResearchResultKind


@dataclass(frozen=True, slots=True)
class EffectiveResearchLimits:
    max_search_results: int
    max_sources_to_extract: int
    result_kind: ResearchResultKind


@dataclass(frozen=True, slots=True)
class McpResearchPolicy:
    server_max_search_results: int = 20
    server_max_sources_to_extract: int = 10

    def __post_init__(self) -> None:
        if not 1 <= self.server_max_search_results <= 20:
            raise ValueError("INVALID_CONFIGURED_SEARCH_LIMIT")
        if not 1 <= self.server_max_sources_to_extract <= min(self.server_max_search_results, 10):
            raise ValueError("INVALID_CONFIGURED_EXTRACTION_LIMIT")

    def effective_limits(
        self,
        mode: ResearchMode,
        requested_search_results: int | None,
        requested_extractions: int | None,
    ) -> EffectiveResearchLimits:
        mode_search, mode_extract, result_kind = {
            ResearchMode.QUICK: (5, 2, ResearchResultKind.RESEARCH_ANSWER),
            ResearchMode.VERIFIED: (10, 5, ResearchResultKind.EVIDENCE_BUNDLE),
            ResearchMode.DEEP: (
                20,
                10,
                ResearchResultKind.EVIDENCE_BUNDLE_WITH_CONFLICT_ANALYSIS,
            ),
        }[mode]
        search = min(requested_search_results or mode_search, mode_search)
        search = min(search, self.server_max_search_results)
        extractions = min(requested_extractions or mode_extract, mode_extract)
        extractions = min(extractions, self.server_max_sources_to_extract, search)
        return EffectiveResearchLimits(search, extractions, result_kind)
