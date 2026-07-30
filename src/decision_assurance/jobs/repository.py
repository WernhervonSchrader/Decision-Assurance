from __future__ import annotations

from typing import Protocol

from ..production.contracts import ResearchJob
from ..tenancy import TenantContext
from .contracts import ClaimedJob, LeaseToken


class JobRepository(Protocol):
    def enqueue(self, tenant: TenantContext, job: ResearchJob) -> ResearchJob: ...
    def claim(self, worker_id: str, *, now: str) -> ClaimedJob | None: ...
    def heartbeat(
        self, tenant: TenantContext, job_id: str, lease_token: LeaseToken, *, now: str
    ) -> None: ...
    def complete(
        self,
        tenant: TenantContext,
        job_id: str,
        lease_token: LeaseToken,
        *,
        partial: bool,
        now: str,
    ) -> None: ...
    def fail(
        self,
        tenant: TenantContext,
        job_id: str,
        lease_token: LeaseToken,
        reason_code: str,
        *,
        retryable: bool,
        now: str,
    ) -> None: ...
    def cancel(self, tenant: TenantContext, job_id: str, *, now: str) -> ResearchJob: ...
    def recover_stale(self, *, now: str) -> int: ...
    def is_cancelled(self, tenant: TenantContext, job_id: str) -> bool: ...
