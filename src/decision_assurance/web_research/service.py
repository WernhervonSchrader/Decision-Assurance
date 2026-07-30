from __future__ import annotations

import uuid
from dataclasses import dataclass

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


class ResearchSubmissionService:
    """Prepares durable Research work without calling an external provider."""

    def __init__(self, orchestrator: ResearchOrchestrator, jobs: JobRepository):
        self._orchestrator = orchestrator
        self._jobs = jobs

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
        run = self._orchestrator.prepare(
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
        job = self._jobs.enqueue(tenant, proposed)
        replayed = run.status is not ResearchStatus.CREATED or job != proposed
        return SubmittedResearch(run, job, replayed)
