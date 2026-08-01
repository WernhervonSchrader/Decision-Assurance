from __future__ import annotations

import threading
from collections.abc import Mapping, Set

from ..tenancy import TenantContext
from .contracts import DeletionRequest, DeletionStatus, LifecycleEvent
from .ports import LegalHoldActive, LifecycleTransitionConflict


class InMemoryLifecycleRepository:
    def __init__(self, cases: Mapping[str, Set[str]] | None = None):
        self._cases = {tenant: set(values) for tenant, values in (cases or {}).items()}
        self._requests: dict[tuple[str, str], DeletionRequest] = {}
        self._idempotency: dict[tuple[str, str, str], str] = {}
        self._holds: set[tuple[str, str]] = set()
        self.events: list[LifecycleEvent] = []
        self._lock = threading.RLock()

    def add_case(self, tenant: TenantContext, decision_id: str) -> None:
        self._cases.setdefault(tenant.tenant_id, set()).add(decision_id)

    def case_exists(self, tenant: TenantContext, decision_id: str) -> bool:
        return decision_id in self._cases.get(tenant.tenant_id, set())

    def get_by_idempotency(
        self, tenant: TenantContext, actor_hash: str, key_hash: str
    ) -> DeletionRequest | None:
        request_id = self._idempotency.get((tenant.tenant_id, actor_hash, key_hash))
        return None if request_id is None else self._requests[(tenant.tenant_id, request_id)]

    def get_request(self, tenant: TenantContext, request_id: str) -> DeletionRequest | None:
        return self._requests.get((tenant.tenant_id, request_id))

    def persist_transition(
        self,
        request: DeletionRequest,
        event: LifecycleEvent,
        expected_status: DeletionStatus | None,
    ) -> DeletionRequest:
        key = (request.tenant_id, request.request_id)
        with self._lock:
            current = self._requests.get(key)
            if current is not None:
                if expected_status is None:
                    if (
                        current.case_ref_hash != request.case_ref_hash
                        or current.actor_hash != request.actor_hash
                        or current.idempotency_key_hash != request.idempotency_key_hash
                        or current.reason_code != request.reason_code
                    ):
                        raise LifecycleTransitionConflict("IDEMPOTENCY_KEY_REUSED")
                    return current
                if current.status is not expected_status:
                    if current.status in {request.status, DeletionStatus.COMPLETED}:
                        return current
                    raise LifecycleTransitionConflict("LIFECYCLE_STATUS_CONFLICT")
                if event.previous_event_hash != current.event_hash:
                    raise LifecycleTransitionConflict("LIFECYCLE_EVENT_CHAIN_CONFLICT")
            elif expected_status is not None:
                raise LifecycleTransitionConflict("LIFECYCLE_STATUS_CONFLICT")
            elif event.previous_event_hash is not None:
                raise LifecycleTransitionConflict("LIFECYCLE_EVENT_CHAIN_CONFLICT")
            self._requests[key] = request
            self._idempotency[
                (request.tenant_id, request.actor_hash, request.idempotency_key_hash)
            ] = request.request_id
            self.events.append(event)
            return request

    def active_hold(self, tenant: TenantContext, decision_id: str) -> bool:
        return (tenant.tenant_id, decision_id) in self._holds

    def set_hold(
        self,
        tenant: TenantContext,
        decision_id: str,
        hold_id: str,
        actor_hash: str,
        reason_code: str,
        occurred_at: str,
        event: LifecycleEvent,
    ) -> bool:
        del hold_id, actor_hash, reason_code, occurred_at
        with self._lock:
            key = (tenant.tenant_id, decision_id)
            if key in self._holds:
                return False
            prior = self.last_hold_event(tenant, event.request_id)
            if event.previous_event_hash != (None if prior is None else prior.event_hash):
                raise LifecycleTransitionConflict("LIFECYCLE_EVENT_CHAIN_CONFLICT")
            self._holds.add(key)
            self.events.append(event)
            return True

    def release_hold(
        self,
        tenant: TenantContext,
        decision_id: str,
        actor_hash: str,
        occurred_at: str,
        event: LifecycleEvent,
    ) -> bool:
        del actor_hash, occurred_at
        with self._lock:
            key = (tenant.tenant_id, decision_id)
            if key not in self._holds:
                return False
            prior = self.last_hold_event(tenant, event.request_id)
            if event.previous_event_hash != (None if prior is None else prior.event_hash):
                raise LifecycleTransitionConflict("LIFECYCLE_EVENT_CHAIN_CONFLICT")
            self._holds.remove(key)
            self.events.append(event)
            return True

    def last_event(self, tenant: TenantContext, request_id: str) -> LifecycleEvent | None:
        return next(
            (
                event
                for event in reversed(self.events)
                if event.tenant_id == tenant.tenant_id and event.request_id == request_id
            ),
            None,
        )

    def last_hold_event(self, tenant: TenantContext, hold_id: str) -> LifecycleEvent | None:
        return self.last_event(tenant, hold_id)

    def complete_deletion(self, request: DeletionRequest, event: LifecycleEvent) -> DeletionRequest:
        with self._lock:
            key = (request.tenant_id, request.request_id)
            current = self._requests.get(key)
            if current is None or current.status is not DeletionStatus.EXECUTING:
                if current is not None and current.status is DeletionStatus.COMPLETED:
                    return current
                raise LifecycleTransitionConflict("LIFECYCLE_STATUS_CONFLICT")
            decision_id = current.decision_id
            if decision_id is None:
                raise LifecycleTransitionConflict("LIFECYCLE_STATUS_CONFLICT")
            if event.previous_event_hash != current.event_hash:
                raise LifecycleTransitionConflict("LIFECYCLE_EVENT_CHAIN_CONFLICT")
            tenant = TenantContext(request.tenant_id)
            if self.active_hold(tenant, decision_id):
                raise LegalHoldActive("LEGAL_HOLD_ACTIVE")
            self._requests[key] = request
            self.events.append(event)
            self._cases.setdefault(request.tenant_id, set()).discard(decision_id)
            return request
