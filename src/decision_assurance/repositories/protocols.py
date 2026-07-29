from __future__ import annotations

from typing import Any, Protocol

from ..tenancy import TenantContext

IdempotencyWrite = tuple[str, str, str, str, int, dict[str, Any]]


class DecisionRepository(Protocol):
    def ready(self) -> bool: ...
    def create_decision(
        self,
        tenant: TenantContext,
        document: dict[str, Any],
        events: list[dict[str, Any]] | None = None,
        idempotency: IdempotencyWrite | None = None,
    ) -> None: ...
    def get_decision(self, tenant: TenantContext, decision_id: str) -> dict[str, Any] | None: ...
    def save_result(
        self,
        tenant: TenantContext,
        document: dict[str, Any],
        report: dict[str, Any] | None,
        events: list[dict[str, Any]],
        idempotency: IdempotencyWrite | None = None,
    ) -> None: ...
    def get_report(self, tenant: TenantContext, decision_id: str) -> dict[str, Any] | None: ...
    def list_audit(
        self, tenant: TenantContext, decision_id: str, *, limit: int, offset: int
    ) -> list[dict[str, Any]]: ...
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
        self, tenant: TenantContext, actor_id: str, operation: str, key: str, request_hash: str
    ) -> tuple[int, dict[str, Any]] | None: ...
