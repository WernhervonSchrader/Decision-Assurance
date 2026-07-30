from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from ..audit import payload_hash
from ..authorization import AuthorizationDenied, Permission, authorize
from ..identity import Identity
from ..jobs.repository import JobRepository
from ..repositories.protocols import DecisionRepository
from ..web_research.contracts import FreshnessPolicy, ResearchRequest, ResearchRun
from ..web_research.lifecycle import ResearchTransitionRejected
from ..web_research.orchestrator import ResearchOrchestrator
from ..web_research.ports import ResearchRepositoryPort
from ..web_research.repository import (
    ResearchIdempotencyConflict,
    ResearchIdempotencyInProgress,
)
from ..web_research.service import ResearchSubmissionService
from .contracts import (
    MCP_SCHEMA_VERSION,
    ResearchEvidenceView,
    ResearchGetInput,
    ResearchMode,
    ResearchMutationInput,
    ResearchResultKind,
    ResearchRunView,
    ResearchSourceView,
    ResearchStartInput,
    ResearchToolResponse,
    ToolError,
)
from .policy import McpResearchPolicy


class McpApplicationError(RuntimeError):
    def __init__(self, code: str, reason_code: str | None = None):
        super().__init__(code)
        self.code = code
        self.reason_code = reason_code


class McpResearchService:
    """Transport-independent bounded adapter over existing Research services."""

    def __init__(
        self,
        decisions: DecisionRepository,
        research: ResearchRepositoryPort,
        orchestrator: ResearchOrchestrator,
        *,
        submission: ResearchSubmissionService | None = None,
        jobs: JobRepository | None = None,
        policy: McpResearchPolicy | None = None,
    ):
        self._decisions = decisions
        self._research = research
        self._orchestrator = orchestrator
        self._submission = submission
        self._jobs = jobs
        configured = orchestrator.policy
        self._policy = policy or McpResearchPolicy(
            configured.max_search_results, configured.max_extractions
        )

    async def start(self, identity: Identity, request: ResearchStartInput) -> ResearchToolResponse:
        self._require(identity, Permission.RESEARCH_CREATE)
        correlation_id = str(uuid.uuid4())
        operation = "mcp:research_start"
        digest = payload_hash(request.model_dump(mode="json"))
        document = self._decisions.get_decision(identity.tenant, request.target_id)
        if document is None:
            raise McpApplicationError("NOT_FOUND")
        if document["status"] != "DRAFT":
            raise McpApplicationError("CONFLICT", "DECISION_NOT_DRAFT")
        claim_ids = {str(item["id"]) for item in document["claims"]}
        if not set(request.claim_refs).issubset(claim_ids):
            raise McpApplicationError("INVALID_REQUEST", "CLAIM_REFERENCE_NOT_FOUND")
        limits = self._policy.effective_limits(
            request.mode,
            request.max_search_results,
            request.max_sources_to_extract,
        )
        replay = self._begin(identity, operation, request.idempotency_key, digest)
        if replay is not None:
            return replay
        contract = ResearchRequest(
            decision_file_id=request.target_id,
            claim_refs=tuple(request.claim_refs),
            query=request.query,
            locale=request.locale,
            preferred_languages=tuple(request.preferred_languages),
            max_search_results=limits.max_search_results,
            max_sources_to_extract=limits.max_sources_to_extract,
            allowed_domains=tuple(request.allowed_domains),
            blocked_domains=tuple(request.blocked_domains),
            freshness=FreshnessPolicy(request.maximum_age_days, True),
            research_policy=(
                "standard" if request.mode is ResearchMode.QUICK else "high-assurance"
            ),
        )
        try:
            if self._submission is None:
                run = await self._orchestrator.execute(
                    identity.tenant,
                    identity.actor_id,
                    contract,
                    payload_hash(document),
                    correlation_id,
                )
                job_id = None
                job_status = None
            else:
                submitted = self._submission.submit(
                    identity.tenant,
                    identity.actor_id,
                    contract,
                    payload_hash(document),
                    correlation_id,
                )
                run = submitted.run
                job_id = submitted.job.job_id
                job_status = submitted.job.status.value
        except ValueError as error:
            self._release(identity, operation, request.idempotency_key, digest)
            raise McpApplicationError("INVALID_REQUEST", self._safe_reason(error)) from error
        except Exception:
            self._release(identity, operation, request.idempotency_key, digest)
            raise
        response = self._success(
            run,
            mode=request.mode,
            result_kind=limits.result_kind,
            job_id=job_id,
            job_status=job_status,
        )
        self._finish(identity, operation, request.idempotency_key, digest, response)
        return response

    def get(self, identity: Identity, request: ResearchGetInput) -> ResearchToolResponse:
        self._require(identity, Permission.RESEARCH_READ)
        run = self._required(identity, request.research_run_id)
        return self._success(run)

    async def retry(
        self, identity: Identity, request: ResearchMutationInput
    ) -> ResearchToolResponse:
        self._require(identity, Permission.RESEARCH_RETRY)
        if self._jobs is not None:
            operation, digest, replay = self._mutation_begin(identity, request, "research_retry")
            if replay is not None:
                return replay
            correlation_id = str(uuid.uuid4())
            try:
                run = self._orchestrator.validate_retry(identity.tenant, request.research_run_id)
                job_id = "job-" + str(uuid.uuid5(uuid.NAMESPACE_URL, run.research_run_id))
                job = self._jobs.requeue(
                    identity.tenant,
                    job_id,
                    correlation_id,
                    now=datetime.now(timezone.utc).isoformat(),
                )
            except (KeyError, ResearchTransitionRejected, ValueError) as error:
                self._release(identity, operation, request.idempotency_key, digest)
                raise McpApplicationError("CONFLICT", self._safe_reason(error)) from error
            except Exception:
                self._release(identity, operation, request.idempotency_key, digest)
                raise
            response = self._success(
                run,
                job_id=job.job_id,
                job_status=job.status.value,
            )
            self._finish(identity, operation, request.idempotency_key, digest, response)
            return response
        return await self._mutate_async(
            identity,
            request,
            "research_retry",
            lambda correlation_id: self._orchestrator.retry(
                identity.tenant,
                identity.actor_id,
                request.research_run_id,
                correlation_id,
            ),
        )

    def cancel(self, identity: Identity, request: ResearchMutationInput) -> ResearchToolResponse:
        self._require(identity, Permission.RESEARCH_CANCEL)
        operation, digest, replay = self._mutation_begin(identity, request, "research_cancel")
        if replay is not None:
            return replay
        correlation_id = str(uuid.uuid4())
        try:
            run = self._orchestrator.cancel(
                identity.tenant,
                identity.actor_id,
                request.research_run_id,
                correlation_id,
            )
            if self._jobs is not None:
                job_id = "job-" + str(uuid.uuid5(uuid.NAMESPACE_URL, run.research_run_id))
                try:
                    self._jobs.cancel(identity.tenant, job_id, now=run.updated_at)
                except (KeyError, ValueError):
                    pass
        except (ResearchTransitionRejected, ValueError) as error:
            self._release(identity, operation, request.idempotency_key, digest)
            raise McpApplicationError("CONFLICT", self._safe_reason(error)) from error
        except Exception:
            self._release(identity, operation, request.idempotency_key, digest)
            raise
        response = self._success(run)
        self._finish(identity, operation, request.idempotency_key, digest, response)
        return response

    def handoff(self, identity: Identity, request: ResearchMutationInput) -> ResearchToolResponse:
        self._require(identity, Permission.RESEARCH_HANDOFF)
        operation, digest, replay = self._mutation_begin(identity, request, "research_handoff")
        if replay is not None:
            return replay
        correlation_id = str(uuid.uuid4())
        try:
            run = self._orchestrator.handoff(
                identity.tenant,
                identity.actor_id,
                request.research_run_id,
                correlation_id,
            )
        except (ResearchTransitionRejected, ValueError) as error:
            self._release(identity, operation, request.idempotency_key, digest)
            raise McpApplicationError("CONFLICT", self._safe_reason(error)) from error
        except Exception:
            self._release(identity, operation, request.idempotency_key, digest)
            raise
        response = self._success(run)
        self._finish(identity, operation, request.idempotency_key, digest, response)
        return response

    async def _mutate_async(
        self,
        identity: Identity,
        request: ResearchMutationInput,
        action: str,
        operation_call: Callable[[str], Awaitable[ResearchRun]],
    ) -> ResearchToolResponse:
        operation, digest, replay = self._mutation_begin(identity, request, action)
        if replay is not None:
            return replay
        try:
            run = await operation_call(str(uuid.uuid4()))
        except (ResearchTransitionRejected, ValueError) as error:
            self._release(identity, operation, request.idempotency_key, digest)
            raise McpApplicationError("CONFLICT", self._safe_reason(error)) from error
        except Exception:
            self._release(identity, operation, request.idempotency_key, digest)
            raise
        response = self._success(run)
        self._finish(identity, operation, request.idempotency_key, digest, response)
        return response

    def _required(self, identity: Identity, run_id: str) -> ResearchRun:
        run = self._research.get(identity.tenant, run_id)
        if run is None:
            raise McpApplicationError("NOT_FOUND")
        return run

    def _mutation_begin(
        self, identity: Identity, request: ResearchMutationInput, action: str
    ) -> tuple[str, str, ResearchToolResponse | None]:
        self._required(identity, request.research_run_id)
        operation = f"mcp:{action}:{request.research_run_id}"
        digest = payload_hash(request.model_dump(mode="json"))
        return operation, digest, self._begin(identity, operation, request.idempotency_key, digest)

    def _begin(
        self,
        identity: Identity,
        operation: str,
        key: str,
        digest: str,
    ) -> ResearchToolResponse | None:
        try:
            replay = self._research.reserve_idempotency(
                identity.tenant, identity.actor_id, operation, key, digest
            )
        except ResearchIdempotencyConflict as error:
            raise McpApplicationError("CONFLICT", "IDEMPOTENCY_KEY_REUSED") from error
        except ResearchIdempotencyInProgress as error:
            raise McpApplicationError("CONFLICT", "IDEMPOTENCY_REQUEST_IN_PROGRESS") from error
        return None if replay is None else ResearchToolResponse.model_validate(replay[1])

    def _finish(
        self,
        identity: Identity,
        operation: str,
        key: str,
        digest: str,
        response: ResearchToolResponse,
    ) -> None:
        self._research.complete_idempotency(
            identity.tenant,
            identity.actor_id,
            operation,
            key,
            digest,
            200,
            response.model_dump(mode="json"),
        )

    def _release(
        self,
        identity: Identity,
        operation: str,
        key: str,
        digest: str,
    ) -> None:
        self._research.release_idempotency(
            identity.tenant,
            identity.actor_id,
            operation,
            key,
            digest,
        )

    @staticmethod
    def _require(identity: Identity, permission: Permission) -> None:
        try:
            authorize(identity, permission)
        except AuthorizationDenied as error:
            raise McpApplicationError("FORBIDDEN") from error

    @staticmethod
    def _success(
        run: ResearchRun,
        *,
        mode: ResearchMode | None = None,
        result_kind: ResearchResultKind | None = None,
        job_id: str | None = None,
        job_status: str | None = None,
    ) -> ResearchToolResponse:
        evidence = [
            ResearchEvidenceView(
                evidence_id=item.evidence_id,
                claim_refs=list(item.claim_refs),
                source_id=item.source_id,
                snapshot_id=item.snapshot_id,
                content_hash=item.content_hash,
                freshness_status=item.assessment.freshness_status,
                conflict_status=item.assessment.conflict_status,
                usable_for_decision=item.assessment.usable_for_decision,
                requires_human_review=item.assessment.requires_human_review,
                prompt_injection_suspected=item.risk.prompt_injection_suspected,
                reason_codes=list(item.assessment.reason_codes),
            )
            for item in run.evidence
        ]
        conflicts = [item.evidence_id for item in evidence if item.conflict_status == "CONFLICTING"]
        view = ResearchRunView(
            research_run_id=run.research_run_id,
            decision_file_id=run.request.decision_file_id,
            status=run.status.value,
            mode=mode,
            result_kind=result_kind,
            created_at=run.created_at,
            updated_at=run.updated_at,
            correlation_id=run.correlation_id,
            audit_event_ids=[item.event_id for item in run.audit_events],
            source_count=len(run.sources),
            evidence_count=len(run.evidence),
            provider_cost_units=run.provider_cost_units,
            compiled_decision_file_id=run.compiled_decision_file_id,
            requires_human_review=bool(conflicts)
            or any(item.requires_human_review for item in evidence),
            sources=[
                ResearchSourceView(
                    source_id=item.source_id,
                    canonical_url=item.canonical_url,
                    domain=item.domain,
                    title=item.title,
                    rank=item.rank,
                    extraction_status=item.status,
                    reason_codes=list(item.reason_codes),
                )
                for item in run.sources
            ],
            evidence_bundle_draft=evidence,
            conflict_evidence_ids=conflicts,
            error_codes=[item.reason_code for item in run.errors],
            job_id=job_id,
            job_status=job_status,
        )
        return ResearchToolResponse(
            schema_version=MCP_SCHEMA_VERSION,
            ok=True,
            correlation_id=run.correlation_id,
            result=view,
        )

    @staticmethod
    def error_response(error: McpApplicationError, locale: str) -> ResearchToolResponse:
        from ..i18n import localize, select_locale

        correlation_id = str(uuid.uuid4())
        selected = select_locale(locale)
        return ResearchToolResponse(
            schema_version=MCP_SCHEMA_VERSION,
            ok=False,
            correlation_id=correlation_id,
            error=ToolError(
                code=error.code,
                message=localize(error.code, selected),
                reason_code=error.reason_code,
            ),
        )

    @staticmethod
    def internal_error(locale: str) -> ResearchToolResponse:
        return McpResearchService.error_response(McpApplicationError("INTERNAL_ERROR"), locale)

    @staticmethod
    def _safe_reason(error: Exception) -> str:
        value = str(error)
        if value and len(value) <= 128 and value.replace("_", "").isalnum():
            return value
        return "OPERATION_REJECTED"
