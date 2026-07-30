from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from decision_assurance.production.contracts import ResearchJob
from decision_assurance.tenancy import TenantContext
from decision_assurance.web_research.contracts import ResearchStatus
from decision_assurance.web_research.service import ResearchSubmissionService


class FakeOrchestrator:
    def __init__(self, run: Any):
        self.run = run
        self.prepare_calls = 0

    def prepare(self, *args: Any, **kwargs: Any) -> Any:
        self.prepare_calls += 1
        return self.run


class FakeJobs:
    def __init__(self):
        self.enqueued: list[ResearchJob] = []

    def enqueue(self, tenant: TenantContext, job: ResearchJob) -> ResearchJob:
        self.enqueued.append(job)
        return job


def test_submission_only_prepares_and_enqueues_without_provider_execution() -> None:
    research_run = SimpleNamespace(
        research_run_id="research-1",
        tenant_id="tenant-a",
        actor_id="actor-a",
        request=object(),
        correlation_id="correlation-a",
        status=ResearchStatus.CREATED,
        created_at="2026-07-30T10:00:00Z",
        updated_at="2026-07-30T10:00:00Z",
    )
    orchestrator = FakeOrchestrator(research_run)
    jobs = FakeJobs()
    service = ResearchSubmissionService(orchestrator, jobs)  # type: ignore[arg-type]

    submitted = service.submit(
        TenantContext(research_run.tenant_id),
        research_run.actor_id,
        research_run.request,
        "sha256:" + "a" * 64,
        research_run.correlation_id,
    )

    assert orchestrator.prepare_calls == 1
    assert len(jobs.enqueued) == 1
    assert submitted.job.research_run_id == research_run.research_run_id
