from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from decision_assurance.identity import ActorKind, Role
from decision_assurance.oidc.authenticator import AuthenticationFailed, OidcAuthenticator
from decision_assurance.oidc.jwks import CachedJwksProvider
from decision_assurance.production.contracts import OidcPolicy

ISSUER = "https://identity.example.test"
AUDIENCE = "decision-assurance"


def _key(kid: str) -> tuple[Any, dict[str, Any]]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(private.public_key(), as_dict=True)
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return private, jwk


def _claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    values: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "human-1",
        "iat": now,
        "nbf": now - 1,
        "exp": now + 300,
        "tenant_id": "tenant-a",
        "role": "APPROVER",
        "actor_kind": "HUMAN",
        "organization": "org-a",
        "groups": ["reviewers", "sales"],
    }
    values.update(overrides)
    return values


def _authenticator(
    handler: Callable[[httpx.Request], httpx.Response], *, cache_ttl_seconds: int = 300
) -> OidcAuthenticator:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = CachedJwksProvider(
        issuer=ISSUER,
        jwks_uri=f"{ISSUER}/.well-known/jwks.json",
        client=client,
        cache_ttl_seconds=cache_ttl_seconds,
    )
    return OidcAuthenticator(
        OidcPolicy(
            issuer=ISSUER,
            audience=AUDIENCE,
            algorithms=("RS256",),
            organization_claim="organization",
            groups_claim="groups",
        ),
        provider,
    )


def test_valid_signed_token_maps_identity_only_from_verified_claims() -> None:
    private, public = _key("key-1")
    authenticator = _authenticator(lambda request: httpx.Response(200, json={"keys": [public]}))
    token = jwt.encode(_claims(), private, algorithm="RS256", headers={"kid": "key-1"})

    identity = authenticator.authenticate(token)

    assert identity.actor_id == "human-1"
    assert identity.tenant.tenant_id == "tenant-a"
    assert identity.role is Role.APPROVER
    assert identity.kind is ActorKind.HUMAN
    assert identity.organization_id == "org-a"
    assert identity.groups == ("reviewers", "sales")


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://attacker.example"},
        {"aud": "wrong-audience"},
        {"exp": 1},
        {"nbf": int(time.time()) + 3600},
        {"tenant_id": ""},
        {"role": "ROOT"},
        {"actor_kind": "ROBOT"},
        {"sub": ""},
        {"groups": "reviewers"},
    ],
)
def test_invalid_registered_or_mapped_claims_fail_closed(overrides: dict[str, Any]) -> None:
    private, public = _key("key-1")
    authenticator = _authenticator(lambda request: httpx.Response(200, json={"keys": [public]}))
    token = jwt.encode(_claims(**overrides), private, algorithm="RS256", headers={"kid": "key-1"})

    with pytest.raises(AuthenticationFailed, match="INVALID_TOKEN"):
        authenticator.authenticate(token)


def test_manipulated_payload_and_unsigned_tokens_are_rejected() -> None:
    private, public = _key("key-1")
    other_private, _ = _key("other")
    authenticator = _authenticator(lambda request: httpx.Response(200, json={"keys": [public]}))
    manipulated = jwt.encode(
        _claims(tenant_id="tenant-b"),
        other_private,
        algorithm="RS256",
        headers={"kid": "key-1"},
    )
    unsigned = jwt.encode(_claims(), key="", algorithm="none", headers={"kid": "key-1"})
    confused = jwt.encode(
        _claims(),
        key="not-a-public-key-but-long-enough-123",
        algorithm="HS256",
        headers={"kid": "key-1"},
    )

    for token in (manipulated, unsigned, confused):
        with pytest.raises(AuthenticationFailed, match="INVALID_TOKEN"):
            authenticator.authenticate(token)


def test_unknown_kid_refreshes_once_and_supports_key_rotation() -> None:
    first_private, first_public = _key("key-1")
    second_private, second_public = _key("key-2")
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        keys = [first_public] if calls == 1 else [first_public, second_public]
        return httpx.Response(200, json={"keys": keys})

    authenticator = _authenticator(handler)
    first = jwt.encode(
        _claims(sub="first"), first_private, algorithm="RS256", headers={"kid": "key-1"}
    )
    second = jwt.encode(
        _claims(sub="second"), second_private, algorithm="RS256", headers={"kid": "key-2"}
    )

    assert authenticator.authenticate(first).actor_id == "first"
    assert authenticator.authenticate(second).actor_id == "second"
    assert calls == 2


def test_unknown_key_or_jwks_outage_fails_without_disclosing_provider_details() -> None:
    private, public = _key("key-1")
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"keys": [public]})
        raise httpx.ConnectError("provider detail must stay private", request=request)

    authenticator = _authenticator(handler)
    valid = jwt.encode(_claims(), private, algorithm="RS256", headers={"kid": "key-1"})
    unknown = jwt.encode(_claims(), private, algorithm="RS256", headers={"kid": "unknown"})
    assert authenticator.authenticate(valid).tenant.tenant_id == "tenant-a"

    with pytest.raises(AuthenticationFailed) as captured:
        authenticator.authenticate(unknown)

    assert str(captured.value) == "INVALID_TOKEN"


def test_duplicate_key_ids_are_rejected_as_a_poisoned_jwks_document() -> None:
    private, public = _key("duplicate")
    authenticator = _authenticator(
        lambda request: httpx.Response(200, json={"keys": [public, public]})
    )
    token = jwt.encode(_claims(), private, algorithm="RS256", headers={"kid": "duplicate"})

    with pytest.raises(AuthenticationFailed, match="INVALID_TOKEN"):
        authenticator.authenticate(token)
