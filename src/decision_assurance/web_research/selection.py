from __future__ import annotations

from collections.abc import Collection, Sequence

from .contracts import SourceCandidate


class SourceSelectionPolicy:
    """Deterministic, provider-neutral source selection."""

    def select(
        self,
        sources: Sequence[SourceCandidate],
        *,
        limit: int,
        statuses: Collection[str] = ("DISCOVERED",),
    ) -> tuple[SourceCandidate, ...]:
        eligible = (item for item in sources if item.status in statuses)
        return tuple(sorted(eligible, key=lambda item: (item.rank, item.source_id))[:limit])
