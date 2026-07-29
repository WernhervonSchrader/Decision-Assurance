from __future__ import annotations

from typing import cast

from fastapi import Header, Request

from ..authorization import AuthorizationDenied, Permission, authorize
from ..identity import Identity
from .errors import ApiError


def get_identity(request: Request, authorization: str | None = Header(default=None)) -> Identity:
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(401, "UNAUTHENTICATED")
    try:
        return cast(Identity, request.app.state.authenticator.authenticate(authorization[7:]))
    except ValueError as error:
        raise ApiError(401, "UNAUTHENTICATED") from error


def require(identity: Identity, permission: Permission) -> None:
    try:
        authorize(identity, permission)
    except AuthorizationDenied as error:
        raise ApiError(403, "FORBIDDEN") from error


def require_idempotency_key(value: str | None) -> str:
    if value is None or not 1 <= len(value) <= 128:
        raise ApiError(422, "INVALID_REQUEST", {"field": "Idempotency-Key"})
    return value
