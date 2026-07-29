from __future__ import annotations


class NoOpResearchMetrics:
    def increment(self, name: str, *, tags: dict[str, str] | None = None) -> None:
        del name, tags

    def observe(self, name: str, value: float, *, tags: dict[str, str] | None = None) -> None:
        del name, value, tags
