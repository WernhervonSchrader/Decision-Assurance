from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..web_research.contracts import FreshnessPolicy, ResearchRequest


class ResearchFreshnessBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maximum_age_days: int = Field(default=365, ge=1, le=3650)
    prefer_recent: bool = True


class ResearchRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["0.4.0"]
    decision_file_id: str = Field(min_length=1, max_length=256)
    claim_refs: list[str] = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1, max_length=400)
    locale: str = Field(min_length=2, max_length=35)
    preferred_languages: list[str] = Field(min_length=1, max_length=5)
    max_search_results: int = Field(ge=1, le=20)
    max_sources_to_extract: int = Field(ge=1, le=10)
    allowed_domains: list[str] = Field(default_factory=list, max_length=50)
    blocked_domains: list[str] = Field(default_factory=list, max_length=50)
    freshness: ResearchFreshnessBody
    research_policy: Literal["standard", "high-assurance"]
    force_refresh: bool
    refresh_generation: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_limits(self) -> ResearchRequestBody:
        if self.max_sources_to_extract > self.max_search_results:
            raise ValueError("INVALID_EXTRACTION_LIMIT")
        if len(set(self.claim_refs)) != len(self.claim_refs):
            raise ValueError("INVALID_CLAIM_REFS")
        if self.force_refresh != (self.refresh_generation is not None):
            raise ValueError("INVALID_REFRESH_GENERATION")
        return self

    def to_contract(self) -> ResearchRequest:
        return ResearchRequest(
            self.decision_file_id,
            tuple(self.claim_refs),
            self.query,
            self.locale,
            tuple(self.preferred_languages),
            self.max_search_results,
            self.max_sources_to_extract,
            tuple(self.allowed_domains),
            tuple(self.blocked_domains),
            FreshnessPolicy(self.freshness.maximum_age_days, self.freshness.prefer_recent),
            self.research_policy,
            self.force_refresh,
            self.schema_version,
        )


class EmptyResearchAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
