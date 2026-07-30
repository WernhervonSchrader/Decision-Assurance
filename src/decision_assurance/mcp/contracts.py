from __future__ import annotations

from enum import Enum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MCP_SCHEMA_VERSION: Final[Literal["0.5.0"]] = "0.5.0"


class ResearchMode(str, Enum):
    QUICK = "QUICK"
    VERIFIED = "VERIFIED"
    DEEP = "DEEP"


class ResearchResultKind(str, Enum):
    RESEARCH_ANSWER = "RESEARCH_ANSWER"
    EVIDENCE_BUNDLE = "EVIDENCE_BUNDLE"
    EVIDENCE_BUNDLE_WITH_CONFLICT_ANALYSIS = "EVIDENCE_BUNDLE_WITH_CONFLICT_ANALYSIS"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResearchStartInput(StrictModel):
    schema_version: Literal["0.5.0"] = MCP_SCHEMA_VERSION
    decision_file_id: str | None = Field(default=None, min_length=1, max_length=256)
    case_id: str | None = Field(default=None, min_length=1, max_length=256)
    claim_refs: list[str] = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1, max_length=400)
    locale: str = Field(min_length=2, max_length=35)
    preferred_languages: list[str] = Field(min_length=1, max_length=5)
    mode: ResearchMode
    maximum_age_days: int = Field(default=365, ge=1, le=3650)
    allowed_domains: list[str] = Field(default_factory=list, max_length=50)
    blocked_domains: list[str] = Field(default_factory=list, max_length=50)
    max_search_results: int | None = Field(default=None, ge=1, le=20)
    max_sources_to_extract: int | None = Field(default=None, ge=1, le=10)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_target_and_limits(self) -> ResearchStartInput:
        if (self.decision_file_id is None) == (self.case_id is None):
            raise ValueError("EXACTLY_ONE_RESEARCH_TARGET_REQUIRED")
        if len(set(self.claim_refs)) != len(self.claim_refs):
            raise ValueError("INVALID_CLAIM_REFS")
        if self.max_search_results is not None and self.max_sources_to_extract is not None:
            if self.max_sources_to_extract > self.max_search_results:
                raise ValueError("INVALID_EXTRACTION_LIMIT")
        return self

    @property
    def target_id(self) -> str:
        value = self.decision_file_id or self.case_id
        if value is None:  # pragma: no cover - guarded by validation
            raise ValueError("RESEARCH_TARGET_REQUIRED")
        return value


class ResearchGetInput(StrictModel):
    schema_version: Literal["0.5.0"] = MCP_SCHEMA_VERSION
    research_run_id: str = Field(min_length=1, max_length=256)
    locale: str = Field(default="en", min_length=2, max_length=35)


class ResearchMutationInput(ResearchGetInput):
    idempotency_key: str = Field(min_length=1, max_length=128)


class ToolError(StrictModel):
    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=300)
    reason_code: str | None = Field(default=None, min_length=1, max_length=128)


class ResearchSourceView(StrictModel):
    source_id: str
    canonical_url: str
    domain: str
    title: str
    rank: int
    extraction_status: str
    reason_codes: list[str]


class ResearchEvidenceView(StrictModel):
    evidence_id: str
    claim_refs: list[str]
    source_id: str
    snapshot_id: str
    content_hash: str
    freshness_status: str
    conflict_status: str
    usable_for_decision: bool
    requires_human_review: bool
    prompt_injection_suspected: bool
    reason_codes: list[str]


class ResearchRunView(StrictModel):
    research_run_id: str
    decision_file_id: str
    status: str
    mode: ResearchMode | None = None
    result_kind: ResearchResultKind | None = None
    created_at: str
    updated_at: str
    correlation_id: str
    audit_event_ids: list[str]
    source_count: int
    evidence_count: int
    provider_cost_units: int
    compiled_decision_file_id: str | None
    requires_human_review: bool
    sources: list[ResearchSourceView]
    evidence_bundle_draft: list[ResearchEvidenceView]
    conflict_evidence_ids: list[str]
    error_codes: list[str]
    job_id: str | None = None
    job_status: str | None = None


class ResearchToolResponse(StrictModel):
    schema_version: Literal["0.5.0"] = MCP_SCHEMA_VERSION
    ok: bool
    correlation_id: str
    result: ResearchRunView | None = None
    error: ToolError | None = None

    @model_validator(mode="after")
    def validate_result_or_error(self) -> ResearchToolResponse:
        if self.ok != (self.result is not None) or self.ok == (self.error is not None):
            raise ValueError("INVALID_TOOL_RESPONSE")
        return self
