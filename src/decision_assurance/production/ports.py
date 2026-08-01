from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from ..identity import Identity
from ..jobs.contracts import ClaimedJob, LeaseToken
from ..tenancy import TenantContext
from .contracts import (
    GateResult,
    HealthComponent,
    ResearchJob,
    SecretReference,
    SecretValue,
)


class IdentityProviderPort(Protocol):
    def authenticate(self, token: str) -> Identity: ...


class PersistenceReadinessPort(Protocol):
    def ready(self) -> bool: ...
    def verify_tenant_scope(self, tenant: TenantContext) -> bool: ...


class MigrationPort(Protocol):
    def current_version(self) -> str: ...
    def migrate(self, target_version: str) -> None: ...


class JobRepositoryPort(Protocol):
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


class SecretProviderPort(Protocol):
    def resolve(self, reference: SecretReference) -> SecretValue: ...


class EgressPolicyPort(Protocol):
    def validate(self, tenant: TenantContext, url: str) -> str: ...


class StructuredLoggerPort(Protocol):
    def emit(
        self,
        event_type: str,
        *,
        level: str,
        correlation_id: str,
        fields: Mapping[str, str | int | float | bool | None],
    ) -> None: ...


class MetricsPort(Protocol):
    def increment(self, name: str, *, labels: Mapping[str, str] | None = None) -> None: ...
    def observe(
        self, name: str, value: float, *, labels: Mapping[str, str] | None = None
    ) -> None: ...
    def set_gauge(
        self, name: str, value: float, *, labels: Mapping[str, str] | None = None
    ) -> None: ...
    def render_prometheus(self) -> str: ...


class HealthProbePort(Protocol):
    def check(self) -> HealthComponent: ...


class BackupProviderPort(Protocol):
    def create_backup(self, destination: str) -> str: ...
    def restore(self, backup_ref: str, destination: str) -> None: ...
    def verify(self, backup_ref: str) -> tuple[GateResult, ...]: ...
