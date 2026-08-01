from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from decision_assurance.api.app import create_app
from decision_assurance.identity import ActorKind, Role
from decision_assurance.oidc.authenticator import AuthenticationFailed, OidcAuthenticator
from decision_assurance.oidc.jwks import CachedJwksProvider
from decision_assurance.production.contracts import OidcPolicy

ISSUER = "https://identity.example.test"
AUDIENCE = "decision-assurance"

EXTERNAL_ROLE_MAP = {
    "da_admin": Role.SYSTEM_ADMINISTRATOR,
    "tenant_admin": Role.TENANT_ADMIN,
    "decision_author": Role.GENERATOR,
    "decision_reviewer": Role.VALIDATOR,
    "decision_approver": Role.APPROVER,
    "auditor": Role.AUDITOR,
    "research_operator": Role.RESEARCH_OPERATOR,
    "readonly": Role.READONLY,
}


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
        "realm_access": {"roles": ["decision_approver", "decision_author"]},
        "actor_kind": "HUMAN",
        "organization": "org-a",
        "groups": ["reviewers", "sales"],
        "azp": "decision-assurance-e2e",
        "scope": "openid da.api",
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
            role_claim="realm_access.roles",
            organization_claim="organization",
            groups_claim="groups",
            authorized_parties=("decision-assurance-ui", "decision-assurance-e2e"),
            required_scopes=("da.api",),
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
    assert identity.roles == frozenset({Role.APPROVER, Role.GENERATOR})
    assert identity.kind is ActorKind.HUMAN
    assert identity.organization_id == "org-a"
    assert identity.groups == ("reviewers", "sales")
    assert identity.client_id == "decision-assurance-e2e"
    assert identity.scopes == frozenset({"openid", "da.api"})


@pytest.mark.parametrize(("external_role", "expected"), EXTERNAL_ROLE_MAP.items())
def test_only_exact_external_keycloak_roles_are_mapped(external_role: str, expected: Role) -> None:
    private, public = _key("exact-role")
    authenticator = _authenticator(lambda request: httpx.Response(200, json={"keys": [public]}))
    token = jwt.encode(
        _claims(realm_access={"roles": [external_role]}),
        private,
        algorithm="RS256",
        headers={"kid": "exact-role"},
    )

    identity = authenticator.authenticate(token)

    assert identity.roles == frozenset({expected})


@pytest.mark.parametrize(
    "external_role",
    ["TENANT_ADMIN", "Tenant_Admin", "tenant-admin", *(role.value for role in Role)],
)
def test_internal_or_normalized_role_names_are_rejected(external_role: str) -> None:
    private, public = _key("invalid-role")
    authenticator = _authenticator(lambda request: httpx.Response(200, json={"keys": [public]}))
    token = jwt.encode(
        _claims(realm_access={"roles": [external_role]}),
        private,
        algorithm="RS256",
        headers={"kid": "invalid-role"},
    )

    with pytest.raises(AuthenticationFailed, match="AUTH_ROLE_REQUIRED"):
        authenticator.authenticate(token)


def test_unknown_role_beside_exact_valid_role_adds_no_permission() -> None:
    private, public = _key("mixed-role")
    authenticator = _authenticator(lambda request: httpx.Response(200, json={"keys": [public]}))
    token = jwt.encode(
        _claims(realm_access={"roles": ["unknown", "readonly"]}),
        private,
        algorithm="RS256",
        headers={"kid": "mixed-role"},
    )

    identity = authenticator.authenticate(token)

    assert identity.role is Role.READONLY
    assert identity.roles == frozenset({Role.READONLY})


def test_signed_token_without_exact_role_is_denied_before_repository_access() -> None:
    class SpyRepository:
        def __init__(self) -> None:
            self.calls = 0

        def ready(self) -> bool:
            return True

        def get_decision(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs
            self.calls += 1
            return None

    private, public = _key("pre-access-role")
    authenticator = _authenticator(lambda request: httpx.Response(200, json={"keys": [public]}))
    token = jwt.encode(
        _claims(realm_access={"roles": ["TENANT_ADMIN"]}),
        private,
        algorithm="RS256",
        headers={"kid": "pre-access-role"},
    )
    repository = SpyRepository()
    client = TestClient(create_app(repository, authenticator))  # type: ignore[arg-type]

    response = client.get("/v1/decisions/D-1", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["details"]["reason_code"] == "AUTH_ROLE_REQUIRED"
    assert repository.calls == 0


def test_valid_signing_key_is_selected_when_jwks_also_contains_encryption_key() -> None:
    private, signing_key = _key("signing-key")
    _, encryption_key = _key("encryption-key")
    encryption_key.update({"use": "enc", "alg": "RSA-OAEP"})
    authenticator = _authenticator(
        lambda request: httpx.Response(200, json={"keys": [encryption_key, signing_key]})
    )
    token = jwt.encode(_claims(), private, algorithm="RS256", headers={"kid": "signing-key"})

    assert authenticator.authenticate(token).actor_id == "human-1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://attacker.example"},
        {"aud": "wrong-audience"},
        {"exp": 1},
        {"nbf": int(time.time()) + 3600},
        {"tenant_id": ""},
        {"realm_access": {"roles": ["ROOT"]}},
        {"actor_kind": "ROBOT"},
        {"sub": ""},
        {"groups": "reviewers"},
        {"azp": "untrusted-client"},
        {"scope": "openid"},
    ],
)
def test_invalid_registered_or_mapped_claims_fail_closed(overrides: dict[str, Any]) -> None:
    private, public = _key("key-1")
    authenticator = _authenticator(lambda request: httpx.Response(200, json={"keys": [public]}))
    token = jwt.encode(_claims(**overrides), private, algorithm="RS256", headers={"kid": "key-1"})

    with pytest.raises(AuthenticationFailed):
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
        with pytest.raises(AuthenticationFailed, match="AUTH_TOKEN_INVALID"):
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

    assert str(captured.value) == "AUTH_TOKEN_INVALID"


@pytest.mark.parametrize(
    ("overrides", "reason_code"),
    [
        ({"exp": 1}, "AUTH_TOKEN_EXPIRED"),
        ({"iss": "https://attacker.example"}, "AUTH_ISSUER_MISMATCH"),
        ({"aud": "wrong-audience"}, "AUTH_AUDIENCE_MISMATCH"),
        ({"azp": "untrusted-client"}, "AUTH_TOKEN_INVALID"),
        ({"scope": "openid"}, "AUTH_TOKEN_INVALID"),
        ({"realm_access": {"roles": ["unknown"]}}, "AUTH_ROLE_REQUIRED"),
    ],
)
def test_authentication_failures_have_stable_reason_codes(
    overrides: dict[str, Any], reason_code: str
) -> None:
    private, public = _key("key-1")
    authenticator = _authenticator(lambda request: httpx.Response(200, json={"keys": [public]}))
    token = jwt.encode(_claims(**overrides), private, algorithm="RS256", headers={"kid": "key-1"})

    with pytest.raises(AuthenticationFailed) as captured:
        authenticator.authenticate(token)

    assert captured.value.reason_code == reason_code
    assert str(captured.value) == reason_code


def test_duplicate_key_ids_are_rejected_as_a_poisoned_jwks_document() -> None:
    private, public = _key("duplicate")
    authenticator = _authenticator(
        lambda request: httpx.Response(200, json={"keys": [public, public]})
    )
    token = jwt.encode(_claims(), private, algorithm="RS256", headers={"kid": "duplicate"})

    with pytest.raises(AuthenticationFailed, match="AUTH_TOKEN_INVALID"):
        authenticator.authenticate(token)
