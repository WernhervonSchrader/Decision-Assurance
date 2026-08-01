from __future__ import annotations

from typing import Any

from fastapi import Depends
from fastapi.testclient import TestClient

from decision_assurance.api.app import create_app
from decision_assurance.api.dependencies import get_identity
from decision_assurance.identity import ActorKind, Identity, Role, StaticTokenAuthenticator
from decision_assurance.security_events import InMemorySecurityEventSink, SecurityEvent
from decision_assurance.tenancy import TenantContext


class SpyRepository:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def ready(self) -> bool:
        return True

    def get_decision(self, tenant: TenantContext, decision_id: str) -> None:
        del tenant, decision_id
        self.calls.append("get_decision")
        return None

    def create_decision(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        self.calls.append("create_decision")


def _client(
    role: Role = Role.GENERATOR,
) -> tuple[TestClient, SpyRepository, InMemorySecurityEventSink]:
    repository = SpyRepository()
    events = InMemorySecurityEventSink()
    identity = Identity(
        "actor-a",
        TenantContext("tenant-a"),
        role,
        ActorKind.HUMAN,
        client_id="decision-assurance-e2e",
        scopes=frozenset({"da.api"}),
    )
    app = create_app(  # type: ignore[arg-type]
        repository,
        StaticTokenAuthenticator({"valid-token": identity}),
        security_events=events,
    )
    return TestClient(app), repository, events


def test_security_event_contract_rejects_secret_bearing_or_unknown_data() -> None:
    event = SecurityEvent.create(
        event_type="authentication.failed",
        decision="DENIED",
        actor_ref="anonymous:0123456789abcdef",
        tenant_id=None,
        client_id=None,
        correlation_id="corr-1",
        reason_code="AUTH_TOKEN_INVALID",
    )
    assert event.schema_version == "1.0.0"
    assert set(event.to_dict()) == {
        "event_id",
        "event_type",
        "schema_version",
        "occurred_at",
        "decision",
        "actor_ref",
        "tenant_id",
        "client_id",
        "correlation_id",
        "reason_code",
        "permission",
    }
    raw = repr(event.to_dict()).casefold()
    assert "bearer" not in raw and "authorization" not in raw and "password" not in raw


def test_missing_and_invalid_tokens_emit_stable_secret_free_events() -> None:
    client, repository, events = _client()

    missing = client.get("/v1/decisions/missing", headers={"X-Correlation-ID": "corr-missing"})
    invalid = client.get(
        "/v1/decisions/missing",
        headers={
            "Authorization": "Bearer do-not-log-this-token",
            "X-Correlation-ID": "corr-invalid",
        },
    )

    assert missing.status_code == invalid.status_code == 401
    assert [item.reason_code for item in events.events] == [
        "AUTH_TOKEN_MISSING",
        "AUTH_TOKEN_INVALID",
    ]
    assert "do-not-log-this-token" not in repr(events.events)
    assert repository.calls == []


def test_header_tenant_conflict_is_denied_before_repository_access() -> None:
    client, repository, events = _client()
    response = client.get(
        "/v1/decisions/D-1",
        headers={
            "Authorization": "Bearer valid-token",
            "X-Tenant-ID": "tenant-b",
            "X-Correlation-ID": "corr-tenant-header",
        },
    )

    assert response.status_code == 403
    assert response.json()["details"]["reason_code"] == "AUTH_TENANT_MISMATCH"
    assert repository.calls == []
    assert events.events[-1].reason_code == "AUTH_TENANT_MISMATCH"


def test_path_tenant_conflict_is_denied_before_route_or_repository_access() -> None:
    repository = SpyRepository()
    events = InMemorySecurityEventSink()
    identity = Identity("actor-a", TenantContext("tenant-a"), Role.GENERATOR, ActorKind.HUMAN)
    app = create_app(  # type: ignore[arg-type]
        repository,
        StaticTokenAuthenticator({"valid-token": identity}),
        security_events=events,
    )

    @app.get("/test/tenants/{tenant_id}")
    def tenant_path(tenant_id: str, verified: Identity = Depends(get_identity)) -> dict[str, str]:
        del tenant_id, verified
        repository.calls.append("handler")
        return {"status": "unexpected"}

    response = TestClient(app).get(
        "/test/tenants/tenant-b", headers={"Authorization": "Bearer valid-token"}
    )

    assert response.status_code == 403
    assert repository.calls == []
    assert events.events[-1].reason_code == "AUTH_TENANT_MISMATCH"


def test_body_tenant_conflict_is_denied_before_repository_or_provider_access() -> None:
    client, repository, events = _client()
    response = client.post(
        "/v1/decisions",
        headers={
            "Authorization": "Bearer valid-token",
            "Idempotency-Key": "body-conflict",
            "X-Correlation-ID": "corr-tenant-body",
        },
        json={"tenant_id": "tenant-b"},
    )

    assert response.status_code == 403
    assert repository.calls == []
    assert events.events[-1].reason_code == "AUTH_TENANT_MISMATCH"


def test_missing_role_is_denied_and_audited_before_repository_access() -> None:
    client, repository, events = _client(Role.READONLY)
    response = client.post(
        "/v1/decisions/D-1/evaluate",
        headers={
            "Authorization": "Bearer valid-token",
            "Idempotency-Key": "role-denied",
            "Content-Type": "application/json",
            "X-Correlation-ID": "corr-role",
        },
        json={},
    )

    assert response.status_code == 403
    assert repository.calls == []
    assert events.events[-1].reason_code == "AUTH_ROLE_REQUIRED"
    assert events.events[-1].permission == "decision:evaluate"


def test_transition_role_is_denied_before_repository_access() -> None:
    client, repository, events = _client(Role.READONLY)
    response = client.post(
        "/v1/decisions/D-1/transitions",
        headers={"Authorization": "Bearer valid-token", "Idempotency-Key": "transition-denied"},
        json={"target": "BLOCKED"},
    )

    assert response.status_code == 403
    assert repository.calls == []
    assert events.events[-1].reason_code == "AUTH_ROLE_REQUIRED"


def test_platform_admin_has_no_implicit_cross_tenant_bypass() -> None:
    client, repository, events = _client(Role.SYSTEM_ADMINISTRATOR)
    response = client.get(
        "/v1/decisions/D-1",
        headers={"Authorization": "Bearer valid-token", "X-Tenant-ID": "tenant-b"},
    )

    assert response.status_code == 403
    assert repository.calls == []
    assert events.events[-1].reason_code == "AUTH_CROSS_TENANT_DENIED"
