from __future__ import annotations

from typing import Protocol

from ..tenancy import TenantContext
from .contracts import DeletionRequest, DeletionStatus, LifecycleEvent


class LegalHoldActive(RuntimeError):
    pass


class LifecycleTransitionConflict(RuntimeError):
    pass


class LifecycleRepository(Protocol):
    def case_exists(self, tenant: TenantContext, decision_id: str) -> bool: ...
    def get_by_idempotency(
        self, tenant: TenantContext, actor_hash: str, key_hash: str
    ) -> DeletionRequest | None: ...
    def get_request(self, tenant: TenantContext, request_id: str) -> DeletionRequest | None: ...
    def persist_transition(
        self,
        request: DeletionRequest,
        event: LifecycleEvent,
        expected_status: DeletionStatus | None,
    ) -> DeletionRequest: ...
    def active_hold(self, tenant: TenantContext, decision_id: str) -> bool: ...
    def set_hold(
        self,
        tenant: TenantContext,
        decision_id: str,
        hold_id: str,
        actor_hash: str,
        reason_code: str,
        occurred_at: str,
        event: LifecycleEvent,
    ) -> bool: ...
    def release_hold(
        self,
        tenant: TenantContext,
        decision_id: str,
        actor_hash: str,
        occurred_at: str,
        event: LifecycleEvent,
    ) -> bool: ...
    def last_event(self, tenant: TenantContext, request_id: str) -> LifecycleEvent | None: ...
    def last_hold_event(self, tenant: TenantContext, hold_id: str) -> LifecycleEvent | None: ...
    def complete_deletion(
        self, request: DeletionRequest, event: LifecycleEvent
    ) -> DeletionRequest: ...
