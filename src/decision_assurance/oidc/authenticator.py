from __future__ import annotations

from typing import Any

import jwt

from ..identity import ActorKind, Identity, Role
from ..production.contracts import OidcPolicy
from ..tenancy import TenantContext
from .jwks import CachedJwksProvider


class AuthenticationFailed(ValueError):
    """Generic failure that intentionally hides issuer and key details."""

    def __init__(self, reason_code: str = "AUTH_TOKEN_INVALID"):
        self.reason_code = reason_code
        super().__init__(reason_code)


KEYCLOAK_ROLE_MAP: dict[str, Role] = {
    "da_admin": Role.SYSTEM_ADMINISTRATOR,
    "tenant_admin": Role.TENANT_ADMIN,
    "decision_author": Role.GENERATOR,
    "decision_reviewer": Role.VALIDATOR,
    "decision_approver": Role.APPROVER,
    "auditor": Role.AUDITOR,
    "research_operator": Role.RESEARCH_OPERATOR,
    "readonly": Role.READONLY,
}
_PRIMARY_ROLE_ORDER = (
    Role.APPROVER,
    Role.VALIDATOR,
    Role.GENERATOR,
    Role.TENANT_ADMIN,
    Role.RESEARCH_OPERATOR,
    Role.AUDITOR,
    Role.READONLY,
    Role.SYSTEM_ADMINISTRATOR,
    Role.REVIEWER,
)


class OidcAuthenticator:
    def __init__(self, policy: OidcPolicy, keys: CachedJwksProvider):
        self._policy = policy
        self._keys = keys

    def authenticate(self, token: str) -> Identity:
        try:
            if not token or len(token) > 16_384:
                raise AuthenticationFailed()
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            kid = header.get("kid")
            if algorithm not in self._policy.algorithms or not isinstance(kid, str):
                raise AuthenticationFailed()
            key = self._keys.get(kid, str(algorithm))
            claims = jwt.decode(
                token,
                key,
                algorithms=list(self._policy.algorithms),
                audience=self._policy.audience,
                issuer=self._policy.issuer,
                leeway=self._policy.clock_skew_seconds,
                options={
                    "require": ["iss", "aud", "sub", "iat", "exp"],
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
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("AUTH_TOKEN_EXPIRED") from None
        except jwt.InvalidIssuerError:
            raise AuthenticationFailed("AUTH_ISSUER_MISMATCH") from None
        except jwt.InvalidAudienceError:
            raise AuthenticationFailed("AUTH_AUDIENCE_MISMATCH") from None
        except (jwt.PyJWTError, TypeError, ValueError):
            raise AuthenticationFailed() from None

    def _map_claims(self, claims: dict[str, Any]) -> Identity:
        actor_id = self._required_string(claims, self._policy.actor_id_claim)
        tenant_id = self._required_string(claims, self._policy.tenant_claim)
        roles = self._roles(claims, self._policy.role_claim)
        role = next((item for item in _PRIMARY_ROLE_ORDER if item in roles), None)
        if role is None:
            raise AuthenticationFailed("AUTH_ROLE_REQUIRED")
        kind = ActorKind(self._required_string(claims, self._policy.actor_kind_claim))
        organization_id = self._optional_string(claims, self._policy.organization_claim)
        groups = self._groups(claims, self._policy.groups_claim)
        client_id = self._required_string(claims, "azp")
        if self._policy.authorized_parties and client_id not in self._policy.authorized_parties:
            raise AuthenticationFailed()
        scope_value = self._required_string(claims, "scope")
        scopes = frozenset(scope_value.split())
        if not set(self._policy.required_scopes).issubset(scopes):
            raise AuthenticationFailed()
        return Identity(
            actor_id=actor_id,
            tenant=TenantContext(tenant_id),
            role=role,
            kind=kind,
            organization_id=organization_id,
            groups=groups,
            roles=roles,
            client_id=client_id,
            scopes=scopes,
        )

    @classmethod
    def _claim(cls, claims: dict[str, Any], name: str) -> Any:
        value: Any = claims
        for part in name.split("."):
            if not isinstance(value, dict) or part not in value:
                raise AuthenticationFailed()
            value = value[part]
        return value

    @staticmethod
    def _required_string(claims: dict[str, Any], name: str) -> str:
        value = OidcAuthenticator._claim(claims, name)
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise AuthenticationFailed()
        return value

    @staticmethod
    def _optional_string(claims: dict[str, Any], name: str | None) -> str | None:
        if name is None or name not in claims:
            return None
        value = OidcAuthenticator._claim(claims, name)
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise AuthenticationFailed()
        return value

    @staticmethod
    def _groups(claims: dict[str, Any], name: str | None) -> tuple[str, ...]:
        if name is None or name not in claims:
            return ()
        value = OidcAuthenticator._claim(claims, name)
        if (
            not isinstance(value, list)
            or len(value) > 100
            or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            raise AuthenticationFailed()
        return tuple(value)

    @staticmethod
    def _roles(claims: dict[str, Any], name: str) -> frozenset[Role]:
        value = OidcAuthenticator._claim(claims, name)
        raw_roles = [value] if isinstance(value, str) else value
        if (
            not isinstance(raw_roles, list)
            or not 1 <= len(raw_roles) <= 100
            or any(not isinstance(item, str) or not item.strip() for item in raw_roles)
        ):
            raise AuthenticationFailed("AUTH_ROLE_REQUIRED")
        mapped: set[Role] = set()
        for item in raw_roles:
            mapped_role = KEYCLOAK_ROLE_MAP.get(item)
            if mapped_role is not None:
                mapped.add(mapped_role)
        if not mapped:
            raise AuthenticationFailed("AUTH_ROLE_REQUIRED")
        return frozenset(mapped)
