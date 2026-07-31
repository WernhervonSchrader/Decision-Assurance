from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .tenancy import TenantContext


class Role(str, Enum):
    GENERATOR = "GENERATOR"
    VALIDATOR = "VALIDATOR"
    APPROVER = "APPROVER"
    AUDITOR = "AUDITOR"
    REVIEWER = "REVIEWER"
    TENANT_ADMIN = "TENANT_ADMIN"
    SYSTEM_ADMINISTRATOR = "SYSTEM_ADMINISTRATOR"
    RESEARCH_OPERATOR = "RESEARCH_OPERATOR"
    READONLY = "READONLY"


class ActorKind(str, Enum):
    HUMAN = "HUMAN"
    AGENT = "AGENT"
    SERVICE = "SERVICE"


@dataclass(frozen=True, slots=True)
class Identity:
    actor_id: str
    tenant: TenantContext
    role: Role
    kind: ActorKind
    organization_id: str | None = None
    groups: tuple[str, ...] = ()
    roles: frozenset[Role] = frozenset()
    client_id: str | None = None
    scopes: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.actor_id.strip():
            raise ValueError("INVALID_ACTOR_ID")
        if self.organization_id is not None and not self.organization_id.strip():
            raise ValueError("INVALID_ORGANIZATION_ID")
        if any(not item.strip() for item in self.groups):
            raise ValueError("INVALID_IDENTITY_GROUP")
        effective_roles = self.roles or frozenset({self.role})
        if self.role not in effective_roles:
            raise ValueError("INVALID_PRIMARY_ROLE")
        if self.client_id is not None and not self.client_id.strip():
            raise ValueError("INVALID_CLIENT_ID")
        if any(not item.strip() for item in self.scopes):
            raise ValueError("INVALID_IDENTITY_SCOPE")
        object.__setattr__(self, "roles", effective_roles)


class Authenticator(Protocol):
    def authenticate(self, token: str) -> Identity: ...


class StaticTokenAuthenticator:
    """Deterministic reference adapter; replace with verified OIDC in deployment."""

    def __init__(self, identities: Mapping[str, Identity]):
        self._identities = dict(identities)

    def authenticate(self, token: str) -> Identity:
        identity = self._identities.get(token)
        if identity is None:
            raise ValueError("INVALID_TOKEN")
        return identity
