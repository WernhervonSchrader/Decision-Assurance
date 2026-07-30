from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from ..jobs.repository import JobRepository
from ..production.contracts import JobStatus, ResearchJob
from ..tenancy import TenantContext
from .contracts import ResearchRequest, ResearchRun, ResearchStatus
from .orchestrator import ResearchOrchestrator


@dataclass(frozen=True, slots=True)
class SubmittedResearch:
    run: ResearchRun
    job: ResearchJob
    replayed: bool


class AtomicResearchSubmitter(Protocol):
    def submit(
        self, tenant: TenantContext, run: ResearchRun, job: ResearchJob
    ) -> SubmittedResearch: ...


class ResearchSubmissionService:
    """Prepares durable Research work without calling an external provider."""

    def __init__(
        self,
        orchestrator: ResearchOrchestrator,
        jobs: JobRepository,
        atomic_submitter: AtomicResearchSubmitter | None = None,
    ):
        self._orchestrator = orchestrator
        self._jobs = jobs
        self._atomic_submitter = atomic_submitter

    def submit(
        self,
        tenant: TenantContext,
        actor_id: str,
        request: ResearchRequest,
        expected_document_hash: str,
        correlation_id: str,
        *,
        refresh_generation: str | None = None,
    ) -> SubmittedResearch:
        if self._atomic_submitter is None:
            run = self._orchestrator.prepare(
                tenant,
                actor_id,
                request,
                expected_document_hash,
                correlation_id,
                refresh_generation=refresh_generation,
            )
        else:
            run = self._orchestrator.propose(
                tenant,
                actor_id,
                request,
                expected_document_hash,
                correlation_id,
                refresh_generation=refresh_generation,
            )
        job_id = "job-" + str(uuid.uuid5(uuid.NAMESPACE_URL, run.research_run_id))
        proposed = ResearchJob(
            job_id=job_id,
            tenant_id=tenant.tenant_id,
            research_run_id=run.research_run_id,
            correlation_id=correlation_id,
            payload_hash=expected_document_hash,
            status=JobStatus.QUEUED,
            attempt_count=0,
            available_at=run.created_at,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )
        if self._atomic_submitter is not None:
            return self._atomic_submitter.submit(tenant, run, proposed)
        job = self._jobs.enqueue(tenant, proposed)
        replayed = run.status is not ResearchStatus.CREATED or job != proposed
        return SubmittedResearch(run, job, replayed)
