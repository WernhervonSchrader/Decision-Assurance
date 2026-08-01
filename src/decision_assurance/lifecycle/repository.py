from __future__ import annotations

from collections.abc import Mapping, Set

from ..tenancy import TenantContext
from .contracts import DeletionRequest, LifecycleEvent


class InMemoryLifecycleRepository:
    def __init__(self, cases: Mapping[str, Set[str]] | None = None):
        self._cases = {tenant: set(values) for tenant, values in (cases or {}).items()}
        self._requests: dict[tuple[str, str], DeletionRequest] = {}
        self._idempotency: dict[tuple[str, str, str], str] = {}
        self._holds: set[tuple[str, str]] = set()
        self.events: list[LifecycleEvent] = []

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

    def persist_transition(self, request: DeletionRequest, event: LifecycleEvent) -> None:
        self._requests[(request.tenant_id, request.request_id)] = request
        self._idempotency[(request.tenant_id, request.actor_hash, request.idempotency_key_hash)] = (
            request.request_id
        )
        self.events.append(event)

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
    ) -> None:
        del hold_id, actor_hash, reason_code, occurred_at
        self._holds.add((tenant.tenant_id, decision_id))

    def release_hold(
        self, tenant: TenantContext, decision_id: str, actor_hash: str, occurred_at: str
    ) -> bool:
        del actor_hash, occurred_at
        key = (tenant.tenant_id, decision_id)
        if key not in self._holds:
            return False
        self._holds.remove(key)
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

    def delete_case_data(self, tenant: TenantContext, decision_id: str) -> None:
        self._cases.setdefault(tenant.tenant_id, set()).discard(decision_id)
