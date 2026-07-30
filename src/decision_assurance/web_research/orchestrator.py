from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from ..audit import payload_hash
from ..tenancy import TenantContext
from .audit import apply_transition
from .conflicts import mark_conflicting_evidence
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
    SearchResponse,
    SourceCandidate,
    SourceSnapshot,
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
from .providers.errors import ProviderRequestFailed
from .repository import SqliteResearchRepository
from .selection import SourceSelectionPolicy
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
    max_attempts_per_operation: int = 2
    max_search_results: int = 10
    max_extractions: int = 5

    def __post_init__(self) -> None:
        if not 1 <= self.provider_budget <= 10_000:
            raise ValueError("INVALID_PROVIDER_BUDGET")
        if not 1 <= self.max_attempts_per_operation <= 5:
            raise ValueError("INVALID_PROVIDER_ATTEMPT_LIMIT")
        if not 1 <= self.max_search_results <= 20:
            raise ValueError("INVALID_CONFIGURED_SEARCH_LIMIT")
        if not 1 <= self.max_extractions <= min(self.max_search_results, 10):
            raise ValueError("INVALID_CONFIGURED_EXTRACTION_LIMIT")


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
        selection_policy: SourceSelectionPolicy | None = None,
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
        self._selection = selection_policy or SourceSelectionPolicy()
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
        if request.max_search_results > self._policy.max_search_results:
            raise ValueError("SEARCH_LIMIT_EXCEEDS_CONFIGURATION")
        if request.max_sources_to_extract > self._policy.max_extractions:
            raise ValueError("EXTRACTION_LIMIT_EXCEEDS_CONFIGURATION")
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
        if run.audit_events or run.status is not ResearchStatus.CREATED:
            self._metrics.increment("research.semantic_replay")
            return run

        apply_transition(
            run,
            ResearchStatus.SEARCHING,
            occurred_at=self._time(),
            actor_id=actor_id,
            reason_codes=("SEARCH_STARTED",),
            payload={"query_hash": hashlib.sha256(request.query.encode()).hexdigest()},
        )
        self._repository.save(tenant, run)
        if not await self._discover(tenant, run, actor_id):
            return run
        self._start_extraction(tenant, run, actor_id, retry=False)
        return await self._extract_and_finalize(tenant, run, actor_id, retry_only=False)

    async def retry(
        self,
        tenant: TenantContext,
        actor_id: str,
        run_id: str,
        correlation_id: str,
    ) -> ResearchRun:
        run = self._required(tenant, run_id)
        self._enforce_retry_window(run)
        run.actor_id = actor_id
        run.correlation_id = correlation_id
        if not run.sources:
            apply_transition(
                run,
                ResearchStatus.SEARCHING,
                occurred_at=self._time(),
                actor_id=actor_id,
                reason_codes=("RESEARCH_RETRY_STARTED",),
                payload={"phase": "search"},
                retry=True,
            )
            self._repository.save(tenant, run)
            if not await self._discover(tenant, run, actor_id):
                return run
            self._start_extraction(tenant, run, actor_id, retry=False)
            retry_only = False
        else:
            self._start_extraction(tenant, run, actor_id, retry=True)
            retry_only = True
        return await self._extract_and_finalize(tenant, run, actor_id, retry_only=retry_only)

    def cancel(
        self,
        tenant: TenantContext,
        actor_id: str,
        run_id: str,
        correlation_id: str,
    ) -> ResearchRun:
        run = self._required(tenant, run_id)
        if run.status is ResearchStatus.CANCELLED:
            return run
        run.actor_id = actor_id
        run.correlation_id = correlation_id
        apply_transition(
            run,
            ResearchStatus.CANCELLED,
            occurred_at=self._time(),
            actor_id=actor_id,
            reason_codes=("RESEARCH_CANCELLED",),
            payload={"run_id": run_id},
        )
        self._repository.save(tenant, run)
        return run

    async def _discover(self, tenant: TenantContext, run: ResearchRun, actor_id: str) -> bool:
        if not self._can_attempt(run, "search", None):
            self._record_error(
                run, ProviderError(self._provider_id(self._search), "RETRY_LIMIT_EXCEEDED", False)
            )
            self._fail_run(tenant, run, actor_id, "RETRY_LIMIT_EXCEEDED")
            return False
        try:
            self._reserve(run, tenant, "search", None)
        except ValueError as budget_failure:
            if str(budget_failure) != "BUDGET_EXCEEDED":
                raise
            self._record_error(run, ProviderError("research-budget", "BUDGET_EXCEEDED", False))
            self._fail_run(tenant, run, actor_id, "BUDGET_EXCEEDED")
            return False
        try:
            response = await self._search.search(
                SearchQuery(
                    run.request.query,
                    run.request.locale,
                    run.request.preferred_languages,
                    run.request.max_search_results,
                    run.request.freshness,
                )
            )
        except ProviderRequestFailed as failure:
            self._fail_attempt(run, failure.error)
            self._record_error(run, failure.error)
            self._fail_run(tenant, run, actor_id, failure.error.reason_code)
            return False
        except Exception:
            provider_failure = ProviderError(
                self._provider_id(self._search), "PROVIDER_UNAVAILABLE", True
            )
            self._fail_attempt(run, provider_failure)
            self._record_error(run, provider_failure)
            self._fail_run(tenant, run, actor_id, provider_failure.reason_code)
            return False
        self._succeed_attempt(run)
        self._store_discovery(run, response)
        apply_transition(
            run,
            ResearchStatus.SOURCES_DISCOVERED,
            occurred_at=self._time(),
            actor_id=actor_id,
            reason_codes=("SOURCES_DISCOVERED",),
            payload={"count": len(run.sources)},
        )
        self._repository.save(tenant, run)
        return True

    def _store_discovery(self, run: ResearchRun, response: SearchResponse) -> None:
        policy = self._url_policy.for_domains(
            allowed_domains=run.request.allowed_domains,
            blocked_domains=run.request.blocked_domains,
        )
        seen_urls: set[str] = set()
        for result in response.results[: run.request.max_search_results]:
            try:
                safe = policy.validate(result.url)
            except UrlPolicyRejected as error:
                run.sources.append(
                    SourceCandidate(
                        self._source_id(run.research_run_id, result.url),
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
                    self._source_id(run.research_run_id, safe.canonical_url),
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

    def _start_extraction(
        self, tenant: TenantContext, run: ResearchRun, actor_id: str, *, retry: bool
    ) -> None:
        apply_transition(
            run,
            ResearchStatus.EXTRACTING,
            occurred_at=self._time(),
            actor_id=actor_id,
            reason_codes=("RESEARCH_RETRY_STARTED" if retry else "EXTRACTION_STARTED",),
            payload={"limit": run.request.max_sources_to_extract},
            retry=retry,
        )
        self._repository.save(tenant, run)

    async def _extract_and_finalize(
        self,
        tenant: TenantContext,
        run: ResearchRun,
        actor_id: str,
        *,
        retry_only: bool,
    ) -> ResearchRun:
        policy = self._url_policy.for_domains(
            allowed_domains=run.request.allowed_domains,
            blocked_domains=run.request.blocked_domains,
        )
        statuses = {"FAILED"} if retry_only else {"DISCOVERED"}
        candidates = self._selection.select(
            run.sources,
            limit=run.request.max_sources_to_extract,
            statuses=statuses,
        )
        if not retry_only:
            selected = {item.source_id for item in candidates}
            for item in run.sources:
                if item.status == "DISCOVERED" and item.source_id not in selected:
                    item.status = "SKIPPED_LIMIT"
                    item.reason_codes = ("SOURCE_LIMIT_REACHED",)
        seen_hashes = {item.content_hash for item in run.snapshots}
        for source in candidates:
            snapshot = await self._obtain_snapshot(tenant, run, source, policy)
            if snapshot is None:
                continue
            if snapshot.content_hash in seen_hashes:
                source.status = "DUPLICATE_CONTENT"
                source.reason_codes = ("CONTENT_DUPLICATE",)
                continue
            seen_hashes.add(snapshot.content_hash)
            run.snapshots.append(snapshot)
            assessment = self._evidence_policy.assess(
                snapshot,
                source,
                maximum_age_days=run.request.freshness.maximum_age_days,
                now=self._clock(),
            )
            evidence_id = (
                "research-"
                + hashlib.sha256(
                    f"{run.research_run_id}:{snapshot.content_hash}".encode()
                ).hexdigest()[:24]
            )
            if not any(item.evidence_id == evidence_id for item in run.evidence):
                run.evidence.append(
                    EvidenceCandidate(
                        evidence_id,
                        tenant.tenant_id,
                        run.research_run_id,
                        run.request.decision_file_id,
                        run.request.claim_refs,
                        source.source_id,
                        snapshot.snapshot_id,
                        snapshot.content_hash,
                        assessment,
                        Provenance(
                            source.rank,
                            run.request.query,
                            source.search_provider,
                            source.search_provider_version,
                            snapshot.content_provider,
                            snapshot.content_provider_version,
                            self._evidence_policy.version,
                        ),
                        snapshot.risk,
                    )
                )
            source.status = "EXTRACTED" if assessment.usable_for_decision else "REVIEW_REQUIRED"

        if not run.snapshots:
            self._fail_run(tenant, run, actor_id, "NO_CONTENT_EXTRACTED")
            return run
        apply_transition(
            run,
            ResearchStatus.EVIDENCE_COMPILED,
            occurred_at=self._time(),
            actor_id=actor_id,
            reason_codes=("EVIDENCE_CANDIDATES_COMPILED",),
            payload={"count": len(run.evidence)},
        )
        mark_conflicting_evidence(run)
        compiled = self._compiler.compile(run)
        handoff_failed = False
        if compiled:
            try:
                updated = self._handoff.attach(
                    tenant,
                    run.request.decision_file_id,
                    run.expected_document_hash,
                    compiled,
                )
                run.expected_document_hash = payload_hash(updated)
                run.compiled_decision_file_id = run.request.decision_file_id
            except ValueError as error:
                reason = str(error)
                if reason not in {
                    "DECISION_DOCUMENT_CHANGED",
                    "DECISION_NOT_DRAFT",
                    "CLAIM_REFERENCE_NOT_FOUND",
                    "DECISION_NOT_FOUND",
                }:
                    reason = "EVIDENCE_HANDOFF_REJECTED"
                run.errors.append(ResearchError(reason))
                handoff_failed = True
        partial_statuses = {"BLOCKED", "FAILED", "REJECTED", "REVIEW_REQUIRED"}
        partial = handoff_failed or any(item.status in partial_statuses for item in run.sources)
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

    async def _obtain_snapshot(
        self,
        tenant: TenantContext,
        run: ResearchRun,
        source: SourceCandidate,
        policy: PublicUrlPolicy,
    ) -> SourceSnapshot | None:
        cached = None
        if not run.request.force_refresh:
            cached = self._repository.get_snapshot(
                tenant, source.canonical_url, current_time=self._time()
            )
        if cached is not None:
            return replace(
                cached,
                snapshot_id=f"{source.source_id}:snapshot:{cached.content_hash[7:23]}",
                source_id=source.source_id,
                original_url=source.original_url,
                canonical_url=source.canonical_url,
                domain=source.domain,
            )
        if not self._can_attempt(run, "extract", source.source_id):
            source.status = "FAILED"
            source.reason_codes = ("RETRY_LIMIT_EXCEEDED",)
            self._record_error(
                run,
                ProviderError(self._provider_id(self._extractor), "RETRY_LIMIT_EXCEEDED", False),
                source.source_id,
            )
            return None
        try:
            self._reserve(run, tenant, "extract", source.source_id)
        except ValueError as budget_failure:
            if str(budget_failure) != "BUDGET_EXCEEDED":
                raise
            source.status = "FAILED"
            source.reason_codes = ("BUDGET_EXCEEDED",)
            self._record_error(
                run, ProviderError("research-budget", "BUDGET_EXCEEDED", False), source.source_id
            )
            return None
        try:
            extraction = await self._extractor.extract(
                ExtractionRequest(
                    source.source_id,
                    source.canonical_url,
                    run.request.locale,
                    self._policy.max_content_bytes,
                    self._policy.cache_ttl_seconds,
                )
            )
        except Exception:
            provider_failure = ProviderError(
                self._provider_id(self._extractor), "PROVIDER_UNAVAILABLE", True
            )
            self._fail_attempt(run, provider_failure)
            source.status = "FAILED"
            source.reason_codes = (provider_failure.reason_code,)
            self._record_error(run, provider_failure, source.source_id)
            return None
        if extraction.error:
            self._fail_attempt(run, extraction.error)
            source.status = "FAILED"
            source.reason_codes = (extraction.error.reason_code,)
            self._record_error(run, extraction.error, source.source_id)
            return None
        if extraction.content is None:
            provider_failure = ProviderError(
                self._provider_id(self._extractor), "EMPTY_EXTRACTION_RESPONSE", False
            )
            self._fail_attempt(run, provider_failure)
            source.status = "FAILED"
            source.reason_codes = (provider_failure.reason_code,)
            self._record_error(run, provider_failure, source.source_id)
            return None
        try:
            final_url = policy.validate(extraction.content.canonical_url)
            if final_url.domain != source.domain:
                raise UrlPolicyRejected("CROSS_DOMAIN_REDIRECT")
            snapshot = self._normalizer.normalize(source, extraction.content)
        except (UrlPolicyRejected, EvidenceNormalizationRejected) as failure:
            reason = str(failure)
            source.status = "REJECTED"
            source.reason_codes = (reason,)
            normalization_failure = ProviderError("normalizer", reason, False)
            self._fail_attempt(run, normalization_failure)
            self._record_error(run, normalization_failure, source.source_id)
            return None
        self._succeed_attempt(run)
        return snapshot

    def _fail_run(
        self, tenant: TenantContext, run: ResearchRun, actor_id: str, reason_code: str
    ) -> None:
        apply_transition(
            run,
            ResearchStatus.FAILED,
            occurred_at=self._time(),
            actor_id=actor_id,
            reason_codes=(reason_code,),
            payload={"errors": len(run.errors)},
        )
        self._repository.save(tenant, run)

    def _reserve(
        self,
        run: ResearchRun,
        tenant: TenantContext,
        operation: str,
        source_id: str | None,
    ) -> None:
        used = self._repository.reserve_budget(
            tenant, run.research_run_id, limit=self._policy.provider_budget
        )
        run.provider_cost_units = used
        provider = self._search if operation == "search" else self._extractor
        run.attempts.append(
            ResearchAttempt(
                f"{run.research_run_id}:attempt:{len(run.attempts) + 1}",
                self._provider_id(provider),
                operation,
                "STARTED",
                self._time(),
                source_id,
            )
        )

    def _can_attempt(self, run: ResearchRun, operation: str, source_id: str | None) -> bool:
        used = sum(
            1
            for item in run.attempts
            if item.operation == operation and item.source_id == source_id
        )
        return used < self._policy.max_attempts_per_operation

    @staticmethod
    def _record_error(run: ResearchRun, error: ProviderError, source_id: str | None = None) -> None:
        run.errors.append(ResearchError(error.reason_code, error, source_id))

    @staticmethod
    def _succeed_attempt(run: ResearchRun) -> None:
        item = run.attempts[-1]
        run.attempts[-1] = replace(item, status="SUCCEEDED")

    @staticmethod
    def _fail_attempt(run: ResearchRun, error: ProviderError) -> None:
        item = run.attempts[-1]
        run.attempts[-1] = replace(item, status="FAILED", reason_code=error.reason_code)

    def _required(self, tenant: TenantContext, run_id: str) -> ResearchRun:
        run = self._repository.get(tenant, run_id)
        if run is None:
            raise KeyError("RESEARCH_RUN_NOT_FOUND")
        return run

    def _enforce_retry_window(self, run: ResearchRun) -> None:
        for item in reversed(run.errors):
            if item.provider is None or item.provider.retry_after_seconds is None:
                continue
            failed_attempt = next(
                (attempt for attempt in reversed(run.attempts) if attempt.status == "FAILED"),
                None,
            )
            if failed_attempt is None:
                return
            occurred_at = datetime.fromisoformat(failed_attempt.occurred_at.replace("Z", "+00:00"))
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=timezone.utc)
            retry_at = occurred_at + timedelta(seconds=item.provider.retry_after_seconds)
            if self._clock().astimezone(timezone.utc) < retry_at.astimezone(timezone.utc):
                raise ValueError("PROVIDER_RETRY_AFTER_ACTIVE")
            return

    @staticmethod
    def _provider_id(provider: object) -> str:
        value = getattr(provider, "provider_id", provider.__class__.__name__)
        return value if isinstance(value, str) else provider.__class__.__name__

    def _time(self) -> str:
        return self._clock().astimezone(timezone.utc).isoformat()

    @staticmethod
    def _source_id(run_id: str, url: str) -> str:
        return f"{run_id}:source:{hashlib.sha256(url.encode()).hexdigest()[:16]}"
