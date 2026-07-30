from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from ..tenancy import TenantContext
from .audit import apply_transition
from .contracts import (
    EvidenceCandidate,
    ExtractionRequest,
    Provenance,
    ProviderError,
    ResearchAttempt,
    ResearchError,
    ResearchRequest,
    ResearchRun,
    ResearchStatus,
    SearchQuery,
    SourceCandidate,
)
from .evidence_policy import EvidencePolicy
from .idempotency import semantic_fingerprint
from .metrics import NoOpResearchMetrics
from .normalization import EvidenceNormalizationRejected, EvidenceNormalizer
from .ports import (
    ContentExtractorPort,
    DecisionEvidenceHandoffPort,
    EvidenceCompilerPort,
    ResearchMetricsPort,
    SearchProviderPort,
)
from .repository import SqliteResearchRepository
from .url_policy import PublicUrlPolicy, UrlPolicyRejected

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class ResearchPolicy:
    policy_version: str = "research-policy-v1"
    provider_configuration_version: str = "providers-v1"
    provider_budget: int = 100
    cache_ttl_seconds: int = 86_400
    max_content_bytes: int = 1_000_000


class ResearchOrchestrator:
    def __init__(
        self,
        search_provider: SearchProviderPort,
        content_extractor: ContentExtractorPort,
        repository: SqliteResearchRepository,
        url_policy: PublicUrlPolicy,
        normalizer: EvidenceNormalizer,
        evidence_policy: EvidencePolicy,
        compiler: EvidenceCompilerPort,
        handoff: DecisionEvidenceHandoffPort,
        *,
        policy: ResearchPolicy = ResearchPolicy(),
        metrics: ResearchMetricsPort | None = None,
        clock: Clock = _utc_now,
    ):
        self._search = search_provider
        self._extractor = content_extractor
        self._repository = repository
        self._url_policy = url_policy
        self._normalizer = normalizer
        self._evidence_policy = evidence_policy
        self._compiler = compiler
        self._handoff = handoff
        self._policy = policy
        self._metrics = metrics or NoOpResearchMetrics()
        self._clock = clock

    async def execute(
        self,
        tenant: TenantContext,
        actor_id: str,
        request: ResearchRequest,
        expected_document_hash: str,
        correlation_id: str,
        *,
        refresh_generation: str | None = None,
    ) -> ResearchRun:
        fingerprint = semantic_fingerprint(
            tenant.tenant_id,
            request,
            expected_document_hash,
            self._policy.policy_version,
            self._policy.provider_configuration_version,
            refresh_generation=refresh_generation,
        )
        run_id = "research-" + str(uuid.uuid5(uuid.NAMESPACE_URL, fingerprint))
        now = self._time()
        proposed = ResearchRun(
            run_id,
            tenant.tenant_id,
            actor_id,
            request,
            expected_document_hash,
            fingerprint,
            ResearchStatus.CREATED,
            now,
            now,
            correlation_id,
        )
        run = self._repository.create_or_get(tenant, proposed)
        if (
            run.research_run_id != run_id
            or run.audit_events
            or run.status is not ResearchStatus.CREATED
        ):
            self._metrics.increment("research.semantic_replay")
            return run

        policy = self._url_policy.for_domains(
            allowed_domains=request.allowed_domains, blocked_domains=request.blocked_domains
        )
        apply_transition(
            run,
            ResearchStatus.SEARCHING,
            occurred_at=self._time(),
            actor_id=actor_id,
            reason_codes=("SEARCH_STARTED",),
            payload={"query_hash": hashlib.sha256(request.query.encode()).hexdigest()},
        )
        self._repository.save(tenant, run)
        self._reserve(run, tenant, "search", "search")
        response = await self._search.search(
            SearchQuery(
                request.query,
                request.locale,
                request.preferred_languages,
                request.max_search_results,
                request.freshness,
            )
        )
        self._succeed_attempt(run)

        seen_urls: set[str] = set()
        for result in response.results[: request.max_search_results]:
            try:
                safe = policy.validate(result.url)
            except UrlPolicyRejected as error:
                run.sources.append(
                    SourceCandidate(
                        self._source_id(run_id, result.url),
                        result.url,
                        result.url,
                        "",
                        result.title,
                        result.snippet,
                        result.rank,
                        response.searched_at,
                        response.provider_id,
                        response.provider_version,
                        result.published_at,
                        "BLOCKED",
                        (str(error),),
                    )
                )
                continue
            if safe.canonical_url in seen_urls:
                continue
            seen_urls.add(safe.canonical_url)
            run.sources.append(
                SourceCandidate(
                    self._source_id(run_id, safe.canonical_url),
                    result.url,
                    safe.canonical_url,
                    safe.domain,
                    result.title,
                    result.snippet,
                    result.rank,
                    response.searched_at,
                    response.provider_id,
                    response.provider_version,
                    result.published_at,
                )
            )
        apply_transition(
            run,
            ResearchStatus.SOURCES_DISCOVERED,
            occurred_at=self._time(),
            actor_id=actor_id,
            reason_codes=("SOURCES_DISCOVERED",),
            payload={"count": len(run.sources)},
        )
        apply_transition(
            run,
            ResearchStatus.EXTRACTING,
            occurred_at=self._time(),
            actor_id=actor_id,
            reason_codes=("EXTRACTION_STARTED",),
            payload={"limit": request.max_sources_to_extract},
        )
        self._repository.save(tenant, run)

        seen_hashes: set[str] = set()
        candidates = [item for item in run.sources if item.status == "DISCOVERED"][
            : request.max_sources_to_extract
        ]
        for source in candidates:
            cached = None
            if not request.force_refresh:
                cached = self._repository.get_snapshot(
                    tenant, source.canonical_url, current_time=self._time()
                )
            if cached is None:
                self._reserve(run, tenant, "extract", source.source_id)
                extraction = await self._extractor.extract(
                    ExtractionRequest(
                        source.source_id,
                        source.canonical_url,
                        request.locale,
                        self._policy.max_content_bytes,
                        self._policy.cache_ttl_seconds,
                    )
                )
                if extraction.error:
                    self._fail_attempt(run, extraction.error)
                    source.status = "FAILED"
                    source.reason_codes = (extraction.error.reason_code,)
                    run.errors.append(
                        ResearchError(
                            extraction.error.reason_code, extraction.error, source.source_id
                        )
                    )
                    continue
                if extraction.content is None:
                    provider_error = ProviderError("extractor", "EMPTY_EXTRACTION_RESPONSE", False)
                    self._fail_attempt(run, provider_error)
                    source.status = "FAILED"
                    source.reason_codes = (provider_error.reason_code,)
                    run.errors.append(
                        ResearchError(provider_error.reason_code, provider_error, source.source_id)
                    )
                    continue
                try:
                    final_url = policy.validate(extraction.content.canonical_url)
                    if final_url.domain != source.domain:
                        raise UrlPolicyRejected("CROSS_DOMAIN_REDIRECT")
                    cached = self._normalizer.normalize(source, extraction.content)
                except (UrlPolicyRejected, EvidenceNormalizationRejected) as error:
                    source.status = "REJECTED"
                    source.reason_codes = (str(error),)
                    run.errors.append(ResearchError(str(error), source_id=source.source_id))
                    self._fail_attempt(run, ProviderError("normalizer", str(error), False))
                    continue
                self._succeed_attempt(run)
            else:
                # Cached content is tenant-local but belongs to an earlier run.
                # Give the current run its own source/snapshot identity so all
                # composite foreign keys remain within this run.
                cached = replace(
                    cached,
                    snapshot_id=f"{source.source_id}:snapshot:{cached.content_hash[7:23]}",
                    source_id=source.source_id,
                    original_url=source.original_url,
                    canonical_url=source.canonical_url,
                    domain=source.domain,
                )
            if cached.content_hash in seen_hashes:
                source.status = "DUPLICATE_CONTENT"
                source.reason_codes = ("CONTENT_DUPLICATE",)
                continue
            seen_hashes.add(cached.content_hash)
            if cached not in run.snapshots:
                run.snapshots.append(cached)
            assessment = self._evidence_policy.assess(
                cached,
                source,
                maximum_age_days=request.freshness.maximum_age_days,
                now=self._clock(),
            )
            evidence_id = (
                "research-"
                + hashlib.sha256(f"{run_id}:{cached.content_hash}".encode()).hexdigest()[:24]
            )
            run.evidence.append(
                EvidenceCandidate(
                    evidence_id,
                    tenant.tenant_id,
                    run_id,
                    request.decision_file_id,
                    request.claim_refs,
                    source.source_id,
                    cached.snapshot_id,
                    cached.content_hash,
                    assessment,
                    Provenance(
                        source.rank,
                        request.query,
                        source.search_provider,
                        source.search_provider_version,
                        cached.content_provider,
                        cached.content_provider_version,
                        self._evidence_policy.version,
                    ),
                    cached.risk,
                )
            )
            source.status = "EXTRACTED" if assessment.usable_for_decision else "REVIEW_REQUIRED"

        if not run.snapshots:
            apply_transition(
                run,
                ResearchStatus.FAILED,
                occurred_at=self._time(),
                actor_id=actor_id,
                reason_codes=("NO_CONTENT_EXTRACTED",),
                payload={"errors": len(run.errors)},
            )
            self._repository.save(tenant, run)
            return run

        apply_transition(
            run,
            ResearchStatus.EVIDENCE_COMPILED,
            occurred_at=self._time(),
            actor_id=actor_id,
            reason_codes=("EVIDENCE_CANDIDATES_COMPILED",),
            payload={"count": len(run.evidence)},
        )
        compiled = self._compiler.compile(run)
        if compiled:
            self._handoff.attach(tenant, request.decision_file_id, expected_document_hash, compiled)
            run.compiled_decision_file_id = request.decision_file_id
        partial = any(item.status != "EXTRACTED" for item in run.sources)
        apply_transition(
            run,
            ResearchStatus.PARTIALLY_COMPLETED if partial else ResearchStatus.COMPLETED,
            occurred_at=self._time(),
            actor_id=actor_id,
            reason_codes=("RESEARCH_PARTIALLY_COMPLETED" if partial else "RESEARCH_COMPLETED",),
            payload={"evidence": len(run.evidence), "handoff": len(compiled)},
        )
        self._repository.save(tenant, run)
        self._metrics.increment("research.completed", tags={"status": run.status.value})
        return run

    def _reserve(
        self, run: ResearchRun, tenant: TenantContext, operation: str, source_id: str
    ) -> None:
        used = self._repository.reserve_budget(
            tenant, run.research_run_id, limit=self._policy.provider_budget
        )
        run.provider_cost_units = used
        run.attempts.append(
            ResearchAttempt(
                f"{run.research_run_id}:attempt:{len(run.attempts) + 1}",
                "search" if operation == "search" else "extractor",
                operation,
                "STARTED",
                self._time(),
                None if operation == "search" else source_id,
            )
        )

    @staticmethod
    def _succeed_attempt(run: ResearchRun) -> None:
        item = run.attempts[-1]
        run.attempts[-1] = ResearchAttempt(
            item.attempt_id,
            item.provider_id,
            item.operation,
            "SUCCEEDED",
            item.occurred_at,
            item.source_id,
            item.cost_units,
        )

    @staticmethod
    def _fail_attempt(run: ResearchRun, error: ProviderError) -> None:
        item = run.attempts[-1]
        run.attempts[-1] = ResearchAttempt(
            item.attempt_id,
            item.provider_id,
            item.operation,
            "FAILED",
            item.occurred_at,
            item.source_id,
            item.cost_units,
            error.reason_code,
        )

    def _time(self) -> str:
        return self._clock().astimezone(timezone.utc).isoformat()

    @staticmethod
    def _source_id(run_id: str, url: str) -> str:
        return f"{run_id}:source:{hashlib.sha256(url.encode()).hexdigest()[:16]}"
