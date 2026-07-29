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
    TENANT_ADMIN = "TENANT_ADMIN"


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

    def __post_init__(self) -> None:
        if not self.actor_id.strip():
            raise ValueError("INVALID_ACTOR_ID")


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
