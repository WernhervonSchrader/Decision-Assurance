from __future__ import annotations

from collections.abc import Mapping

import httpx

from ..identity import Authenticator, Identity, StaticTokenAuthenticator
from ..production.contracts import AuthenticationMode, EnvironmentProfile, OidcPolicy
from .authenticator import OidcAuthenticator
from .jwks import CachedJwksProvider


def create_authenticator(
    *,
    profile: EnvironmentProfile,
    mode: AuthenticationMode,
    static_identities: Mapping[str, Identity] | None = None,
    oidc_policy: OidcPolicy | None = None,
    jwks_uri: str | None = None,
    http_client: httpx.Client | None = None,
) -> Authenticator:
    if profile is EnvironmentProfile.PRODUCTION and mode is not AuthenticationMode.OIDC:
        raise ValueError("PRODUCTION_REQUIRES_OIDC")
    if mode is AuthenticationMode.STATIC:
        if not static_identities:
            raise ValueError("STATIC_IDENTITIES_REQUIRED")
        return StaticTokenAuthenticator(static_identities)
    if oidc_policy is None or jwks_uri is None or http_client is None:
        raise ValueError("OIDC_TRUST_INPUT_REQUIRED")
    return OidcAuthenticator(
        oidc_policy,
        CachedJwksProvider(
            issuer=oidc_policy.issuer,
            jwks_uri=jwks_uri,
            client=http_client,
        ),
    )
