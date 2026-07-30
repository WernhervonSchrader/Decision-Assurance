from __future__ import annotations

from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken

from ..identity import ActorKind, Authenticator, Identity, Role
from ..tenancy import TenantContext
from .service import McpApplicationError

REDACTED_TOKEN_SENTINEL = "[REDACTED]"  # noqa: S105 - sentinel, never a credential


class DecisionAssuranceTokenVerifier:
    """Bridge the MCP resource-server middleware to the existing authenticator."""

    def __init__(self, authenticator: Authenticator):
        self._authenticator = authenticator

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            identity = self._authenticator.authenticate(token)
        except ValueError:
            return None
        return AccessToken(
            token=REDACTED_TOKEN_SENTINEL,
            client_id=identity.actor_id,
            subject=identity.actor_id,
            scopes=[identity.role.value],
            claims={
                "actor_id": identity.actor_id,
                "tenant_id": identity.tenant.tenant_id,
                "role": identity.role.value,
                "kind": identity.kind.value,
                "organization_id": identity.organization_id,
                "groups": list(identity.groups),
            },
        )


def current_identity() -> Identity:
    token = get_access_token()
    if token is None or token.claims is None:
        raise McpApplicationError("UNAUTHENTICATED")
    try:
        claims: dict[str, Any] = token.claims
        groups = claims.get("groups", [])
        if not isinstance(groups, list) or any(not isinstance(item, str) for item in groups):
            raise ValueError("INVALID_GROUPS")
        organization_id = claims.get("organization_id")
        if organization_id is not None and not isinstance(organization_id, str):
            raise ValueError("INVALID_ORGANIZATION")
        return Identity(
            actor_id=str(claims["actor_id"]),
            tenant=TenantContext(str(claims["tenant_id"])),
            role=Role(str(claims["role"])),
            kind=ActorKind(str(claims["kind"])),
            organization_id=organization_id,
            groups=tuple(groups),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise McpApplicationError("UNAUTHENTICATED") from error
