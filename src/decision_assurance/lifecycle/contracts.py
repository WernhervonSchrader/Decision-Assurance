from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class DeletionStatus(str, Enum):
    REQUESTED = "REQUESTED"
    BLOCKED_BY_HOLD = "BLOCKED_BY_HOLD"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class DeletionRequest:
    tenant_id: str
    request_id: str
    decision_id: str | None
    case_ref_hash: str
    actor_hash: str
    idempotency_key_hash: str
    status: DeletionStatus
    reason_code: str
    requested_at: str
    completed_at: str | None = None
    legal_hold_active: bool = False
    event_hash: str = ""
    previous_event_hash: str | None = None

    def with_status(
        self,
        status: DeletionStatus,
        *,
        legal_hold_active: bool = False,
        completed_at: str | None = None,
        forget_decision: bool = False,
    ) -> DeletionRequest:
        return replace(
            self,
            status=status,
            legal_hold_active=legal_hold_active,
            completed_at=completed_at,
            decision_id=None if forget_decision else self.decision_id,
        )

    def with_event(self, event: LifecycleEvent) -> DeletionRequest:
        return replace(
            self,
            event_hash=event.event_hash,
            previous_event_hash=event.previous_event_hash,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "0.8.0",
            "request_id": self.request_id,
            "case_ref_hash": self.case_ref_hash,
            "status": self.status.value,
            "requested_at": self.requested_at,
            "completed_at": self.completed_at,
            "reason_code": self.reason_code,
            "legal_hold_active": self.legal_hold_active,
            "event_hash": self.event_hash,
            "previous_event_hash": self.previous_event_hash,
        }


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    tenant_id: str
    event_id: str
    request_id: str
    case_ref_hash: str
    event_type: str
    occurred_at: str
    reason_code: str
    correlation_id: str
    actor_hash: str
    event_hash: str
    previous_event_hash: str | None

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "0.8.0",
            "event_id": self.event_id,
            "request_id": self.request_id,
            "case_ref_hash": self.case_ref_hash,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "reason_code": self.reason_code,
            "correlation_id": self.correlation_id,
            "actor_hash": self.actor_hash,
            "previous_event_hash": self.previous_event_hash,
        }
