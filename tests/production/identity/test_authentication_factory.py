import httpx
import pytest

from decision_assurance.identity import ActorKind, Identity, Role, StaticTokenAuthenticator
from decision_assurance.oidc.factory import create_authenticator
from decision_assurance.production.contracts import (
    AuthenticationMode,
    EnvironmentProfile,
    OidcPolicy,
)
from decision_assurance.tenancy import TenantContext


def test_production_rejects_static_token_authentication() -> None:
    identities = {
        "local": Identity("actor", TenantContext("tenant-a"), Role.GENERATOR, ActorKind.HUMAN)
    }

    with pytest.raises(ValueError, match="PRODUCTION_REQUIRES_OIDC"):
        create_authenticator(
            profile=EnvironmentProfile.PRODUCTION,
            mode=AuthenticationMode.STATIC,
            static_identities=identities,
        )


def test_static_authentication_remains_an_explicit_test_adapter() -> None:
    identities = {
        "local": Identity("actor", TenantContext("tenant-a"), Role.GENERATOR, ActorKind.HUMAN)
    }

    authenticator = create_authenticator(
        profile=EnvironmentProfile.TEST,
        mode=AuthenticationMode.STATIC,
        static_identities=identities,
    )

    assert isinstance(authenticator, StaticTokenAuthenticator)


def test_oidc_requires_all_trust_inputs() -> None:
    policy = OidcPolicy("https://issuer.example", "audience", ("RS256",))
    with pytest.raises(ValueError, match="OIDC_TRUST_INPUT_REQUIRED"):
        create_authenticator(
            profile=EnvironmentProfile.PRODUCTION,
            mode=AuthenticationMode.OIDC,
            oidc_policy=policy,
            http_client=httpx.Client(),
        )
