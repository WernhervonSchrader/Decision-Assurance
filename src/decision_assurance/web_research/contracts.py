from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_LANGUAGE_PATTERN = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")


class ResearchStatus(str, Enum):
    CREATED = "CREATED"
    SEARCHING = "SEARCHING"
    SOURCES_DISCOVERED = "SOURCES_DISCOVERED"
    EXTRACTING = "EXTRACTING"
    EVIDENCE_COMPILED = "EVIDENCE_COMPILED"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class ContentHash:
    value: str

    def __post_init__(self) -> None:
        if not _HASH_PATTERN.fullmatch(self.value):
            raise ValueError("INVALID_CONTENT_HASH")

    @classmethod
    def from_text(cls, text: str) -> ContentHash:
        return cls("sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest())


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    value: str

    def __post_init__(self) -> None:
        if not 1 <= len(self.value) <= 128 or any(ord(char) < 33 for char in self.value):
            raise ValueError("INVALID_IDEMPOTENCY_KEY")


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    maximum_age_days: int = 365
    prefer_recent: bool = True

    def __post_init__(self) -> None:
        if not 1 <= self.maximum_age_days <= 3650:
            raise ValueError("INVALID_FRESHNESS_POLICY")


@dataclass(frozen=True, slots=True)
class ResearchRequest:
    decision_file_id: str
    claim_refs: tuple[str, ...]
    query: str
    locale: str
    preferred_languages: tuple[str, ...]
    max_search_results: int = 10
    max_sources_to_extract: int = 5
    allowed_domains: tuple[str, ...] = ()
    blocked_domains: tuple[str, ...] = ()
    freshness: FreshnessPolicy = field(default_factory=FreshnessPolicy)
    research_policy: str = "standard"
    force_refresh: bool = False
    schema_version: str = "0.4.0"

    def __post_init__(self) -> None:
        if self.schema_version != "0.4.0":
            raise ValueError("UNSUPPORTED_RESEARCH_SCHEMA")
        if not _ID_PATTERN.fullmatch(self.decision_file_id):
            raise ValueError("INVALID_DECISION_FILE_ID")
        if not self.claim_refs or len(set(self.claim_refs)) != len(self.claim_refs):
            raise ValueError("INVALID_CLAIM_REFS")
        query = self.query.strip()
        if not query:
            raise ValueError("QUERY_REQUIRED")
        if len(query) > 400 or len(query.split()) > 50:
            raise ValueError("QUERY_TOO_LONG")
        if not _LANGUAGE_PATTERN.fullmatch(self.locale):
            raise ValueError("INVALID_LOCALE")
        if not 1 <= len(self.preferred_languages) <= 5 or any(
            not _LANGUAGE_PATTERN.fullmatch(item) for item in self.preferred_languages
        ):
            raise ValueError("INVALID_PREFERRED_LANGUAGES")
        if not 1 <= self.max_search_results <= 20:
            raise ValueError("INVALID_SEARCH_LIMIT")
        if not 1 <= self.max_sources_to_extract <= min(self.max_search_results, 10):
            raise ValueError("INVALID_EXTRACTION_LIMIT")
        if len(self.allowed_domains) > 50 or len(self.blocked_domains) > 50:
            raise ValueError("TOO_MANY_DOMAIN_RULES")
        if self.research_policy not in {"standard", "high-assurance"}:
            raise ValueError("INVALID_RESEARCH_POLICY")


@dataclass(frozen=True, slots=True)
class SearchQuery:
    query: str
    locale: str
    preferred_languages: tuple[str, ...]
    count: int
    freshness: FreshnessPolicy


@dataclass(frozen=True, slots=True)
class SearchResult:
    url: str
    title: str
    snippet: str
    rank: int
    published_at: str | None = None


@dataclass(frozen=True, slots=True)
class SearchResponse:
    provider_id: str
    provider_version: str
    searched_at: str
    results: tuple[SearchResult, ...]


@dataclass(slots=True)
class SourceCandidate:
    source_id: str
    original_url: str
    canonical_url: str
    domain: str
    title: str
    snippet: str
    rank: int
    searched_at: str
    search_provider: str
    search_provider_version: str
    published_at: str | None = None
    status: str = "DISCOVERED"
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExtractionRequest:
    source_id: str
    url: str
    locale: str
    max_content_bytes: int
    cache_ttl_seconds: int


@dataclass(frozen=True, slots=True)
class ExtractedContent:
    markdown: str
    title: str
    canonical_url: str
    retrieved_at: str
    mime_type: str
    http_status: int
    language: str
    content_provider: str
    content_provider_version: str
    provider_request_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderError:
    provider_id: str
    reason_code: str
    retryable: bool
    status_code: int | None = None
    retry_after_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class ResearchError:
    reason_code: str
    provider: ProviderError | None = None
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractionResponse:
    content: ExtractedContent | None = None
    error: ProviderError | None = None

    def __post_init__(self) -> None:
        if (self.content is None) == (self.error is None):
            raise ValueError("INVALID_EXTRACTION_RESPONSE")


@dataclass(frozen=True, slots=True)
class ContentRisk:
    prompt_injection_suspected: bool = False
    risk_reasons: tuple[str, ...] = ()
    secret_redacted: bool = False
    active_content_removed: bool = False


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    snapshot_id: str
    source_id: str
    original_url: str
    canonical_url: str
    domain: str
    title: str
    retrieved_at: str
    expires_at: str
    content_hash: str
    http_status: int
    mime_type: str
    format: str
    text: str
    language: str
    content_provider: str
    content_provider_version: str
    risk: ContentRisk


@dataclass(frozen=True, slots=True)
class Provenance:
    search_result_rank: int
    search_query: str
    search_provider: str
    search_provider_version: str
    content_provider: str
    content_provider_version: str
    policy_version: str


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    freshness_status: str
    source_type: str
    authority_score: float
    relevance_score: float
    conflict_status: str
    usable_for_decision: bool
    requires_human_review: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceCandidate:
    evidence_id: str
    tenant_id: str
    research_run_id: str
    decision_file_id: str
    claim_refs: tuple[str, ...]
    source_id: str
    snapshot_id: str
    content_hash: str
    assessment: EvidenceAssessment
    provenance: Provenance
    risk: ContentRisk


@dataclass(frozen=True, slots=True)
class ResearchAttempt:
    attempt_id: str
    provider_id: str
    operation: str
    status: str
    occurred_at: str
    source_id: str | None = None
    cost_units: int = 1
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class ResearchAuditEvent:
    event_id: str
    event_type: str
    occurred_at: str
    tenant_id: str
    actor_id: str
    from_status: ResearchStatus
    to_status: ResearchStatus
    reason_codes: tuple[str, ...]
    correlation_id: str
    payload_hash: str
    previous_event_hash: str | None


@dataclass(slots=True)
class ResearchRun:
    research_run_id: str
    tenant_id: str
    actor_id: str
    request: ResearchRequest
    expected_document_hash: str
    semantic_fingerprint: str
    status: ResearchStatus
    created_at: str
    updated_at: str
    correlation_id: str
    sources: list[SourceCandidate] = field(default_factory=list)
    snapshots: list[SourceSnapshot] = field(default_factory=list)
    evidence: list[EvidenceCandidate] = field(default_factory=list)
    attempts: list[ResearchAttempt] = field(default_factory=list)
    errors: list[ResearchError] = field(default_factory=list)
    audit_events: list[ResearchAuditEvent] = field(default_factory=list)
    provider_cost_units: int = 0
    compiled_decision_file_id: str | None = None


@dataclass(frozen=True, slots=True)
class DecisionEvidence:
    evidence_id: str
    research_run_id: str
    claim_refs: tuple[str, ...]
    source_ref: str
    status: str
    observed_at: str
    content_hash: str


def enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value
