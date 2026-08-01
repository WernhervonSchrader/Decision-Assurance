from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from fastapi import Header, Request

from ..authorization import AuthorizationDenied, Permission, authorize
from ..identity import Identity, Role
from ..security_events import SecurityEvent, SecurityEventSink
from .errors import ApiError


def _events(request: Request) -> SecurityEventSink:
    return cast(SecurityEventSink, request.app.state.security_events)


def _record(
    request: Request,
    *,
    event_type: str,
    decision: str,
    actor_ref: str,
    tenant_id: str | None,
    client_id: str | None,
    reason_code: str,
    permission: str | None = None,
) -> None:
    try:
        _events(request).record(
            SecurityEvent.create(
                event_type=event_type,
                decision=decision,
                actor_ref=actor_ref,
                tenant_id=tenant_id,
                client_id=client_id,
                correlation_id=request.state.correlation_id,
                reason_code=reason_code,
                permission=permission,
            )
        )
    except Exception:
        metrics = request.app.state.metrics
        if metrics is not None:
            metrics.increment("audit_failures_total")
        raise
    if event_type == "authentication.failed" and request.app.state.metrics is not None:
        request.app.state.metrics.increment(
            "authentication_failures_total", labels={"reason": reason_code}
        )


def _anonymous_ref(token: str | None) -> str:
    if not token:
        return "anonymous:missing"
    return f"anonymous:{hashlib.sha256(token.encode('utf-8')).hexdigest()[:16]}"


async def get_identity(
    request: Request, authorization: str | None = Header(default=None)
) -> Identity:
    if not authorization:
        _record(
            request,
            event_type="authentication.failed",
            decision="DENIED",
            actor_ref=_anonymous_ref(None),
            tenant_id=None,
            client_id=None,
            reason_code="AUTH_TOKEN_MISSING",
        )
        raise ApiError(401, "UNAUTHENTICATED", {"reason_code": "AUTH_TOKEN_MISSING"})
    if not authorization.startswith("Bearer "):
        _record(
            request,
            event_type="authentication.failed",
            decision="DENIED",
            actor_ref=_anonymous_ref(authorization),
            tenant_id=None,
            client_id=None,
            reason_code="AUTH_TOKEN_INVALID",
        )
        raise ApiError(401, "UNAUTHENTICATED", {"reason_code": "AUTH_TOKEN_INVALID"})
    token = authorization[7:]
    try:
        identity = cast(Identity, request.app.state.authenticator.authenticate(token))
    except ValueError as error:
        reason_code = cast(str, getattr(error, "reason_code", "AUTH_TOKEN_INVALID"))
        if reason_code not in {
            "AUTH_TOKEN_EXPIRED",
            "AUTH_ISSUER_MISMATCH",
            "AUTH_AUDIENCE_MISMATCH",
            "AUTH_ROLE_REQUIRED",
        }:
            reason_code = "AUTH_TOKEN_INVALID"
        _record(
            request,
            event_type="authentication.failed",
            decision="DENIED",
            actor_ref=_anonymous_ref(token),
            tenant_id=None,
            client_id=None,
            reason_code=reason_code,
        )
        raise ApiError(401, "UNAUTHENTICATED", {"reason_code": reason_code}) from error

    _record(
        request,
        event_type="authentication.succeeded",
        decision="ALLOWED",
        actor_ref=identity.actor_id,
        tenant_id=identity.tenant.tenant_id,
        client_id=identity.client_id,
        reason_code="AUTH_ALLOWED",
    )
    asserted_tenants: list[str] = []
    if header_tenant := request.headers.get("X-Tenant-ID"):
        asserted_tenants.append(header_tenant)
    path_tenant = request.path_params.get("tenant_id")
    if isinstance(path_tenant, str):
        asserted_tenants.append(path_tenant)
    media_type = request.headers.get("content-type", "").split(";", 1)[0].casefold()
    if request.method in {"POST", "PUT", "PATCH"} and (
        media_type == "application/json" or media_type.endswith("+json")
    ):
        try:
            body = cast(Any, await request.json())
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = None
        if isinstance(body, dict) and isinstance(body.get("tenant_id"), str):
            asserted_tenants.append(body["tenant_id"])
    if any(value != identity.tenant.tenant_id for value in asserted_tenants):
        if request.app.state.metrics is not None:
            request.app.state.metrics.increment("tenant_conflicts_total")
        reason_code = (
            "AUTH_CROSS_TENANT_DENIED"
            if Role.SYSTEM_ADMINISTRATOR in identity.roles
            else "AUTH_TENANT_MISMATCH"
        )
        _record(
            request,
            event_type="tenant.denied",
            decision="DENIED",
            actor_ref=identity.actor_id,
            tenant_id=identity.tenant.tenant_id,
            client_id=identity.client_id,
            reason_code=reason_code,
        )
        raise ApiError(403, "FORBIDDEN", {"reason_code": reason_code})
    return identity


def require(request: Request, identity: Identity, permission: Permission) -> None:
    try:
        authorize(identity, permission)
    except AuthorizationDenied as error:
        _record(
            request,
            event_type="authorization.denied",
            decision="DENIED",
            actor_ref=identity.actor_id,
            tenant_id=identity.tenant.tenant_id,
            client_id=identity.client_id,
            reason_code="AUTH_ROLE_REQUIRED",
            permission=permission.value,
        )
        raise ApiError(403, "FORBIDDEN", {"reason_code": "AUTH_ROLE_REQUIRED"}) from error
    _record(
        request,
        event_type="authorization.allowed",
        decision="ALLOWED",
        actor_ref=identity.actor_id,
        tenant_id=identity.tenant.tenant_id,
        client_id=identity.client_id,
        reason_code="AUTH_ALLOWED",
        permission=permission.value,
    )


def require_one_of(
    request: Request, identity: Identity, permissions: tuple[Permission, ...]
) -> Permission:
    for permission in permissions:
        try:
            authorize(identity, permission)
        except AuthorizationDenied:
            continue
        _record(
            request,
            event_type="authorization.allowed",
            decision="ALLOWED",
            actor_ref=identity.actor_id,
            tenant_id=identity.tenant.tenant_id,
            client_id=identity.client_id,
            reason_code="AUTH_ALLOWED",
            permission=permission.value,
        )
        return permission
    denied = "|".join(permission.value for permission in permissions)
    _record(
        request,
        event_type="authorization.denied",
        decision="DENIED",
        actor_ref=identity.actor_id,
        tenant_id=identity.tenant.tenant_id,
        client_id=identity.client_id,
        reason_code="AUTH_ROLE_REQUIRED",
        permission=denied,
    )
    raise ApiError(403, "FORBIDDEN", {"reason_code": "AUTH_ROLE_REQUIRED"})


def require_idempotency_key(value: str | None) -> str:
    if value is None or not 1 <= len(value) <= 128:
        raise ApiError(422, "INVALID_REQUEST", {"field": "Idempotency-Key"})
    return value
