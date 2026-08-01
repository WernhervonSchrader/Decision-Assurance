from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from datetime import datetime, timezone

from ..authorization import Permission, authorize
from ..identity import Identity
from ..production.contracts import SecretValue
from .contracts import DeletionRequest, DeletionStatus, LifecycleEvent
from .ports import LegalHoldActive, LifecycleRepository


class LifecycleConflict(ValueError):
    pass


class PilotLifecycleService:
    def __init__(
        self,
        repository: LifecycleRepository,
        pseudonymization_secret: SecretValue,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self._repository = repository
        self._secret = pseudonymization_secret
        self._clock = clock

    def __repr__(self) -> str:
        return "PilotLifecycleService(**redacted**)"

    def request_deletion(
        self,
        identity: Identity,
        decision_id: str,
        reason_code: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> DeletionRequest:
        authorize(identity, Permission.DATA_DELETE)
        tenant = identity.tenant
        actor_hash = self._digest("actor", tenant.tenant_id, identity.actor_id)
        key_hash = self._digest("idempotency", tenant.tenant_id, idempotency_key)
        case_hash = self._digest("case", tenant.tenant_id, decision_id)
        replay = self._repository.get_by_idempotency(tenant, actor_hash, key_hash)
        if replay is not None:
            if replay.case_ref_hash != case_hash or replay.reason_code != reason_code:
                raise LifecycleConflict("IDEMPOTENCY_KEY_REUSED")
            return replay
        if not self._repository.case_exists(tenant, decision_id):
            raise LifecycleConflict("CASE_NOT_FOUND")
        occurred_at = self._timestamp()
        request_id = (
            "delete-" + self._plain_digest(f"{tenant.tenant_id}\0{actor_hash}\0{key_hash}")[:24]
        )
        hold = self._repository.active_hold(tenant, decision_id)
        request = DeletionRequest(
            tenant_id=tenant.tenant_id,
            request_id=request_id,
            decision_id=decision_id,
            case_ref_hash=case_hash,
            actor_hash=actor_hash,
            idempotency_key_hash=key_hash,
            status=DeletionStatus.BLOCKED_BY_HOLD if hold else DeletionStatus.REQUESTED,
            reason_code=reason_code,
            requested_at=occurred_at,
            legal_hold_active=hold,
        )
        event = self._event(request, "data.deletion-requested", identity, correlation_id)
        request = request.with_event(event)
        return self._repository.persist_transition(request, event, None)

    def execute_deletion(
        self, identity: Identity, request_id: str, correlation_id: str
    ) -> DeletionRequest:
        authorize(identity, Permission.DATA_DELETE)
        request = self._repository.get_request(identity.tenant, request_id)
        if request is None:
            raise LifecycleConflict("CASE_NOT_FOUND")
        if request.status is DeletionStatus.COMPLETED:
            return request
        decision_id = request.decision_id
        if decision_id is None:
            raise LifecycleConflict("INVALID_DELETION_STATE")
        if self._repository.active_hold(identity.tenant, decision_id):
            blocked = request.with_status(DeletionStatus.BLOCKED_BY_HOLD, legal_hold_active=True)
            return self._record(
                blocked,
                "data.deletion-blocked",
                identity,
                correlation_id,
                expected_status=request.status,
            )
        executing = self._record(
            request.with_status(DeletionStatus.EXECUTING),
            "data.deletion-executing",
            identity,
            correlation_id,
            expected_status=request.status,
        )
        try:
            completed = executing.with_status(
                DeletionStatus.COMPLETED,
                completed_at=self._timestamp(),
                forget_decision=True,
            )
            event = self._event(completed, "data.deletion-completed", identity, correlation_id)
            return self._repository.complete_deletion(completed.with_event(event), event)
        except LegalHoldActive:
            blocked = executing.with_status(DeletionStatus.BLOCKED_BY_HOLD, legal_hold_active=True)
            return self._record(
                blocked,
                "data.deletion-blocked",
                identity,
                correlation_id,
                expected_status=executing.status,
            )

    def place_legal_hold(
        self,
        identity: Identity,
        decision_id: str,
        reason_code: str,
        correlation_id: str,
    ) -> None:
        authorize(identity, Permission.LEGAL_HOLD_MANAGE)
        if not self._repository.case_exists(identity.tenant, decision_id):
            raise LifecycleConflict("CASE_NOT_FOUND")
        actor_hash = self._digest("actor", identity.tenant.tenant_id, identity.actor_id)
        hold_id = "hold-" + self._plain_digest(f"{identity.tenant.tenant_id}\0{decision_id}")[:24]
        event = self._hold_event(
            identity, decision_id, hold_id, "data.legal-hold-placed", reason_code, correlation_id
        )
        self._repository.set_hold(
            identity.tenant,
            decision_id,
            hold_id,
            actor_hash,
            reason_code,
            event.occurred_at,
            event,
        )

    def release_legal_hold(self, identity: Identity, decision_id: str, correlation_id: str) -> bool:
        authorize(identity, Permission.LEGAL_HOLD_MANAGE)
        actor_hash = self._digest("actor", identity.tenant.tenant_id, identity.actor_id)
        hold_id = "hold-" + self._plain_digest(f"{identity.tenant.tenant_id}\0{decision_id}")[:24]
        event = self._hold_event(
            identity,
            decision_id,
            hold_id,
            "data.legal-hold-released",
            "LEGAL_HOLD_RELEASED",
            correlation_id,
        )
        released = self._repository.release_hold(
            identity.tenant, decision_id, actor_hash, event.occurred_at, event
        )
        return released

    def _record(
        self,
        request: DeletionRequest,
        event_type: str,
        identity: Identity,
        correlation_id: str,
        *,
        expected_status: DeletionStatus | None = None,
    ) -> DeletionRequest:
        event = self._event(request, event_type, identity, correlation_id)
        updated = request.with_event(event)
        return self._repository.persist_transition(updated, event, expected_status)

    def _hold_event(
        self,
        identity: Identity,
        decision_id: str,
        hold_id: str,
        event_type: str,
        reason_code: str,
        correlation_id: str,
    ) -> LifecycleEvent:
        prior = self._repository.last_hold_event(identity.tenant, hold_id)
        previous = None if prior is None else prior.event_hash
        occurred_at = self._timestamp()
        case_ref_hash = self._digest("case", identity.tenant.tenant_id, decision_id)
        actor_hash = self._digest("actor", identity.tenant.tenant_id, identity.actor_id)
        chain_ref = "root" if previous is None else previous.removeprefix("sha256:")[:16]
        event_id = f"{hold_id}:{event_type}:{occurred_at}:{chain_ref}"
        payload = {
            "event_id": event_id,
            "request_id": hold_id,
            "case_ref_hash": case_ref_hash,
            "event_type": event_type,
            "occurred_at": occurred_at,
            "reason_code": reason_code,
            "correlation_id": correlation_id,
            "actor_hash": actor_hash,
            "previous_event_hash": previous,
        }
        return LifecycleEvent(
            tenant_id=identity.tenant.tenant_id,
            event_id=event_id,
            request_id=hold_id,
            case_ref_hash=case_ref_hash,
            event_type=event_type,
            occurred_at=occurred_at,
            reason_code=reason_code,
            correlation_id=correlation_id,
            actor_hash=actor_hash,
            event_hash="sha256:"
            + self._plain_digest(
                json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            ),
            previous_event_hash=previous,
        )

    def _event(
        self,
        request: DeletionRequest,
        event_type: str,
        identity: Identity,
        correlation_id: str,
    ) -> LifecycleEvent:
        prior = self._repository.last_event(identity.tenant, request.request_id)
        previous = None if prior is None else prior.event_hash
        occurred_at = self._timestamp()
        chain_ref = "root" if previous is None else previous.removeprefix("sha256:")[:16]
        event_id = f"{request.request_id}:{event_type}:{occurred_at}:{chain_ref}"
        payload = {
            "event_id": event_id,
            "request_id": request.request_id,
            "case_ref_hash": request.case_ref_hash,
            "event_type": event_type,
            "occurred_at": occurred_at,
            "reason_code": request.reason_code,
            "correlation_id": correlation_id,
            "actor_hash": request.actor_hash,
            "previous_event_hash": previous,
        }
        event_hash = "sha256:" + self._plain_digest(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        )
        return LifecycleEvent(
            tenant_id=identity.tenant.tenant_id,
            event_id=event_id,
            request_id=request.request_id,
            case_ref_hash=request.case_ref_hash,
            event_type=event_type,
            occurred_at=occurred_at,
            reason_code=request.reason_code,
            correlation_id=correlation_id,
            actor_hash=request.actor_hash,
            event_hash=event_hash,
            previous_event_hash=previous,
        )

    def _digest(self, purpose: str, tenant_id: str, value: str) -> str:
        digest = hmac.new(
            self._secret.value.encode(),
            f"{purpose}\0{tenant_id}\0{value}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return "sha256:" + digest

    @staticmethod
    def _plain_digest(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def _timestamp(self) -> str:
        return self._clock().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
