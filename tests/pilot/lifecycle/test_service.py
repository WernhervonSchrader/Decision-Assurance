from __future__ import annotations

from datetime import datetime, timezone

import pytest

from decision_assurance.identity import ActorKind, Identity, Role
from decision_assurance.lifecycle.repository import InMemoryLifecycleRepository
from decision_assurance.lifecycle.service import LifecycleConflict, PilotLifecycleService
from decision_assurance.production.contracts import SecretValue
from decision_assurance.tenancy import TenantContext

NOW = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)


def _identity(tenant: str, actor: str = "admin") -> Identity:
    return Identity(actor, TenantContext(tenant), Role.TENANT_ADMIN, ActorKind.HUMAN)


def test_delete_physically_removes_case_and_retains_only_minimized_tombstone() -> None:
    repository = InMemoryLifecycleRepository({"tenant-a": {"quote-1"}})
    service = PilotLifecycleService(
        repository, SecretValue("pilot-lifecycle-pepper"), clock=lambda: NOW
    )

    requested = service.request_deletion(
        _identity("tenant-a"), "quote-1", "USER_REQUEST", "delete-once", "correlation-1"
    )
    completed = service.execute_deletion(
        _identity("tenant-a"), requested.request_id, "correlation-1"
    )

    assert completed.status.value == "COMPLETED"
    assert not repository.case_exists(TenantContext("tenant-a"), "quote-1")
    serialized = completed.to_dict()
    assert "quote-1" not in str(serialized)
    assert "admin" not in str(serialized)
    assert serialized["case_ref_hash"].startswith("sha256:")
    assert [event.event_type for event in repository.events] == [
        "data.deletion-requested",
        "data.deletion-executing",
        "data.deletion-completed",
    ]
    assert repository.events[1].previous_event_hash == repository.events[0].event_hash


def test_active_legal_hold_blocks_physical_deletion_and_replay_is_idempotent() -> None:
    repository = InMemoryLifecycleRepository({"tenant-a": {"quote-1"}})
    service = PilotLifecycleService(
        repository, SecretValue("pilot-lifecycle-pepper"), clock=lambda: NOW
    )
    actor = _identity("tenant-a")
    service.place_legal_hold(actor, "quote-1", "LITIGATION", "correlation-1")

    first = service.request_deletion(actor, "quote-1", "USER_REQUEST", "same-key", "c-1")
    replay = service.request_deletion(actor, "quote-1", "USER_REQUEST", "same-key", "c-2")
    blocked = service.execute_deletion(actor, first.request_id, "c-3")

    assert first.request_id == replay.request_id
    assert blocked.status.value == "BLOCKED_BY_HOLD"
    assert repository.case_exists(TenantContext("tenant-a"), "quote-1")
    assert sum(event.event_type == "data.deletion-requested" for event in repository.events) == 1

    blocked_replay = service.execute_deletion(actor, first.request_id, "c-4")
    assert blocked_replay.status.value == "BLOCKED_BY_HOLD"
    assert repository.events[-1].event_id != repository.events[-2].event_id


def test_cross_tenant_request_and_same_key_with_changed_case_fail_closed() -> None:
    repository = InMemoryLifecycleRepository({"tenant-a": {"quote-1"}, "tenant-b": set()})
    service = PilotLifecycleService(
        repository, SecretValue("pilot-lifecycle-pepper"), clock=lambda: NOW
    )

    with pytest.raises(LifecycleConflict, match="CASE_NOT_FOUND"):
        service.request_deletion(
            _identity("tenant-b"), "quote-1", "USER_REQUEST", "delete-once", "c-1"
        )

    service.request_deletion(_identity("tenant-a"), "quote-1", "USER_REQUEST", "delete-once", "c-2")
    repository.add_case(TenantContext("tenant-a"), "quote-2")
    with pytest.raises(LifecycleConflict, match="IDEMPOTENCY_KEY_REUSED"):
        service.request_deletion(
            _identity("tenant-a"), "quote-2", "USER_REQUEST", "delete-once", "c-3"
        )


def test_only_tenant_admin_can_manage_hold_or_delete() -> None:
    repository = InMemoryLifecycleRepository({"tenant-a": {"quote-1"}})
    service = PilotLifecycleService(
        repository, SecretValue("pilot-lifecycle-pepper"), clock=lambda: NOW
    )
    auditor = Identity("auditor", TenantContext("tenant-a"), Role.AUDITOR, ActorKind.HUMAN)

    with pytest.raises(PermissionError, match="FORBIDDEN"):
        service.place_legal_hold(auditor, "quote-1", "LITIGATION", "c-1")
    with pytest.raises(PermissionError, match="FORBIDDEN"):
        service.request_deletion(auditor, "quote-1", "USER_REQUEST", "key", "c-2")


def test_audit_persistence_failure_fails_closed_without_deletion_request() -> None:
    class FailingRepository(InMemoryLifecycleRepository):
        def persist_transition(self, request: object, event: object) -> None:
            del request, event
            raise RuntimeError("AUDIT_PERSISTENCE_FAILED")

    repository = FailingRepository({"tenant-a": {"quote-1"}})
    service = PilotLifecycleService(
        repository, SecretValue("pilot-lifecycle-pepper"), clock=lambda: NOW
    )

    with pytest.raises(RuntimeError, match="AUDIT_PERSISTENCE_FAILED"):
        service.request_deletion(
            _identity("tenant-a"), "quote-1", "USER_REQUEST", "delete-once", "c-1"
        )

    assert repository.events == []
    assert repository.case_exists(TenantContext("tenant-a"), "quote-1")
