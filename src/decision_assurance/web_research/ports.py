from __future__ import annotations

from typing import Any, Protocol

from ..tenancy import TenantContext
from .contracts import (
    DecisionEvidence,
    ExtractionRequest,
    ExtractionResponse,
    ResearchAuditEvent,
    ResearchRequest,
    ResearchRun,
    SearchQuery,
    SearchResponse,
    SourceSnapshot,
)


class SearchProviderPort(Protocol):
    async def search(self, request: SearchQuery) -> SearchResponse: ...


class ContentExtractorPort(Protocol):
    async def extract(self, request: ExtractionRequest) -> ExtractionResponse: ...


class ProviderCircuitPort(Protocol):
    def before_call(self, tenant_id: str, provider_id: str) -> None: ...
    def record_success(self, tenant_id: str, provider_id: str) -> None: ...
    def record_failure(self, tenant_id: str, provider_id: str, *, retryable: bool) -> None: ...


class ResearchRepositoryPort(Protocol):
    def create_or_get(self, tenant: TenantContext, run: ResearchRun) -> ResearchRun: ...
    def get(self, tenant: TenantContext, run_id: str) -> ResearchRun | None: ...
    def save(self, tenant: TenantContext, run: ResearchRun) -> None: ...
    def list_sources(
        self, tenant: TenantContext, run_id: str, *, limit: int, offset: int
    ) -> list[dict[str, Any]]: ...
    def list_evidence(
        self, tenant: TenantContext, run_id: str, *, limit: int, offset: int
    ) -> list[dict[str, Any]]: ...
    def list_audit(self, tenant: TenantContext, run_id: str) -> list[dict[str, Any]]: ...
    def get_snapshot(
        self, tenant: TenantContext, canonical_url: str, *, current_time: str
    ) -> SourceSnapshot | None: ...
    def reserve_budget(self, tenant: TenantContext, run_id: str, *, limit: int) -> int: ...
    def store_idempotency(
        self,
        tenant: TenantContext,
        actor_id: str,
        operation: str,
        key: str,
        request_hash: str,
        status_code: int,
        response: dict[str, Any],
    ) -> None: ...
    def get_idempotency(
        self,
        tenant: TenantContext,
        actor_id: str,
        operation: str,
        key: str,
        request_hash: str,
    ) -> tuple[int, dict[str, Any]] | None: ...


class EvidenceCompilerPort(Protocol):
    def compile(self, run: ResearchRun) -> tuple[DecisionEvidence, ...]: ...


class DecisionEvidenceHandoffPort(Protocol):
    def attach(
        self,
        tenant: TenantContext,
        decision_file_id: str,
        expected_document_hash: str,
        evidence: tuple[DecisionEvidence, ...],
    ) -> dict[str, object]: ...


class ResearchAuditPort(Protocol):
    def append(self, tenant: TenantContext, event: ResearchAuditEvent) -> None: ...


class ResearchMetricsPort(Protocol):
    def increment(self, name: str, *, tags: dict[str, str] | None = None) -> None: ...
    def observe(self, name: str, value: float, *, tags: dict[str, str] | None = None) -> None: ...


class ResearchPolicyRegistryPort(Protocol):
    def get(self, tenant_id: str) -> object | None: ...


class ResearchOrchestratorPort(Protocol):
    async def execute(
        self,
        tenant: TenantContext,
        actor_id: str,
        request: ResearchRequest,
        expected_document_hash: str,
        correlation_id: str,
        *,
        refresh_generation: str | None = None,
    ) -> ResearchRun: ...
