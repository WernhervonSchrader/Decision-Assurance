from __future__ import annotations

from typing import Any

import jwt

from ..identity import ActorKind, Identity, Role
from ..production.contracts import OidcPolicy
from ..tenancy import TenantContext
from .jwks import CachedJwksProvider


class AuthenticationFailed(ValueError):
    """Generic failure that intentionally hides issuer and key details."""


class OidcAuthenticator:
    def __init__(self, policy: OidcPolicy, keys: CachedJwksProvider):
        self._policy = policy
        self._keys = keys

    def authenticate(self, token: str) -> Identity:
        try:
            if not token or len(token) > 16_384:
                raise AuthenticationFailed("INVALID_TOKEN")
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            kid = header.get("kid")
            if algorithm not in self._policy.algorithms or not isinstance(kid, str):
                raise AuthenticationFailed("INVALID_TOKEN")
            key = self._keys.get(kid, str(algorithm))
            claims = jwt.decode(
                token,
                key,
                algorithms=list(self._policy.algorithms),
                audience=self._policy.audience,
                issuer=self._policy.issuer,
                leeway=self._policy.clock_skew_seconds,
                options={
                    "require": ["iss", "aud", "sub", "iat", "nbf", "exp"],
                    "verify_signature": True,
                    "verify_aud": True,
                    "verify_iss": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_nbf": True,
                },
            )
            return self._map_claims(claims)
        except AuthenticationFailed:
            raise
        except (jwt.PyJWTError, TypeError, ValueError):
            raise AuthenticationFailed("INVALID_TOKEN") from None

    def _map_claims(self, claims: dict[str, Any]) -> Identity:
        actor_id = self._required_string(claims, self._policy.actor_id_claim)
        tenant_id = self._required_string(claims, self._policy.tenant_claim)
        role = Role(self._required_string(claims, self._policy.role_claim))
        kind = ActorKind(self._required_string(claims, self._policy.actor_kind_claim))
        organization_id = self._optional_string(claims, self._policy.organization_claim)
        groups = self._groups(claims, self._policy.groups_claim)
        return Identity(
            actor_id=actor_id,
            tenant=TenantContext(tenant_id),
            role=role,
            kind=kind,
            organization_id=organization_id,
            groups=groups,
        )

    @staticmethod
    def _required_string(claims: dict[str, Any], name: str) -> str:
        value = claims.get(name)
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise AuthenticationFailed("INVALID_TOKEN")
        return value

    @staticmethod
    def _optional_string(claims: dict[str, Any], name: str | None) -> str | None:
        if name is None or name not in claims:
            return None
        value = claims[name]
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise AuthenticationFailed("INVALID_TOKEN")
        return value

    @staticmethod
    def _groups(claims: dict[str, Any], name: str | None) -> tuple[str, ...]:
        if name is None or name not in claims:
            return ()
        value = claims[name]
        if (
            not isinstance(value, list)
            or len(value) > 100
            or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            raise AuthenticationFailed("INVALID_TOKEN")
        return tuple(value)
