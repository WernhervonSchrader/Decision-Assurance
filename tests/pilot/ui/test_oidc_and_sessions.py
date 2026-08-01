from __future__ import annotations

import base64
import hashlib
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from decision_assurance.oidc.jwks import CachedJwksProvider
from decision_assurance.pilot_ui.oidc import BrowserOidcError, OidcBrowserClient
from decision_assurance.pilot_ui.session import (
    LoginTransaction,
    LoginTransactionStore,
    SensitiveToken,
    SessionStore,
)

ISSUER = "https://identity.example/realms/decision-assurance"
CLIENT_ID = "decision-assurance-pilot-ui"


def _client(
    nonce: str, *, returned_nonce: str | None = None, jwks_unavailable: bool = False
) -> OidcBrowserClient:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = RSAAlgorithm.to_jwk(private.public_key(), as_dict=True)
    public.update({"kid": "pilot", "alg": "RS256", "use": "sig"})
    now = int(time.time())
    id_token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": "actor-a",
            "iat": now,
            "exp": now + 300,
            "nonce": returned_nonce if returned_nonce is not None else nonce,
        },
        private,
        algorithm="RS256",
        headers={"kid": "pilot"},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/certs"):
            if jwks_unavailable:
                return httpx.Response(503)
            return httpx.Response(200, json={"keys": [public]})
        if request.url.path.endswith("/token"):
            body = request.content.decode()
            assert "grant_type=authorization_code" in body
            assert "code_verifier=" in body
            return httpx.Response(
                200,
                json={
                    "access_token": "access-canary",
                    "id_token": id_token,
                    "token_type": "Bearer",
                    "expires_in": 300,
                    "refresh_token": "ignored-refresh-canary",
                },
            )
        return httpx.Response(404)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    keys = CachedJwksProvider(
        issuer=ISSUER,
        jwks_uri=f"{ISSUER}/protocol/openid-connect/certs",
        client=http,
    )
    return OidcBrowserClient(
        issuer=ISSUER,
        client_id=CLIENT_ID,
        authorization_endpoint=f"{ISSUER}/protocol/openid-connect/auth",
        token_endpoint=f"{ISSUER}/protocol/openid-connect/token",
        redirect_uri="https://research.example/auth/callback",
        keys=keys,
        http_client=http,
    )


def test_login_transaction_uses_s256_and_is_single_use() -> None:
    store = LoginTransactionStore(ttl_seconds=120, capacity=4, clock=lambda: 10.0)
    transaction = store.create("/cases", "browser-binding")
    client = _client(transaction.nonce)
    authorization_url = client.authorization_url(transaction)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(transaction.code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )

    assert f"code_challenge={challenge}" in authorization_url
    assert "code_challenge_method=S256" in authorization_url
    assert "response_type=code" in authorization_url
    assert store.consume(transaction.state, "browser-binding").state == transaction.state
    with pytest.raises(BrowserOidcError, match="OIDC_STATE_INVALID"):
        store.consume(transaction.state, "browser-binding")


def test_code_exchange_validates_nonce_and_discards_refresh_token() -> None:
    transaction = LoginTransactionStore(clock=lambda: 10.0).create("/cases", "browser-binding")
    token_set = _client(transaction.nonce).exchange("code", transaction)

    assert token_set.access_token.value == "access-canary"
    assert "access-canary" not in repr(token_set)
    assert "ignored-refresh-canary" not in repr(token_set)
    assert not hasattr(token_set, "refresh_token")

    with pytest.raises(BrowserOidcError, match="OIDC_NONCE_INVALID"):
        _client(transaction.nonce, returned_nonce="wrong").exchange("code", transaction)


def test_jwks_outage_is_classified_as_provider_unavailable() -> None:
    transaction = LoginTransactionStore(clock=lambda: 10.0).create("/cases", "browser-binding")
    with pytest.raises(BrowserOidcError, match="OIDC_PROVIDER_UNAVAILABLE"):
        _client(transaction.nonce, jwks_unavailable=True).exchange("code", transaction)


@pytest.mark.parametrize("verifier", ["", "short", "a" * 129, "a" * 42 + "!"])
def test_missing_or_invalid_pkce_verifier_fails_before_token_exchange(verifier: str) -> None:
    transaction = LoginTransaction("state", "nonce", verifier, "/cases", time.monotonic() + 60)
    client = _client("nonce")

    with pytest.raises(BrowserOidcError, match="OIDC_PKCE_VERIFIER_INVALID"):
        client.exchange("code", transaction)


def test_session_store_rotates_identifier_expires_and_never_serializes_token() -> None:
    now = [100.0]
    store = SessionStore(ttl_seconds=300, capacity=2, clock=lambda: now[0])
    session = store.create(
        SensitiveToken("token-canary"),
        {
            "actor_id": "actor-a",
            "tenant_id": "tenant-a",
            "actor_kind": "HUMAN",
            "roles": ["GENERATOR"],
        },
        token_expires_in=120,
    )

    assert len(session.session_id) >= 43
    assert session.csrf_token != session.session_id
    assert store.get(session.session_id) is session
    assert "token-canary" not in repr(session)
    assert "token-canary" not in str(session.identity)
    now[0] = 221.0
    assert store.get(session.session_id) is None
    store.destroy(session.session_id)
    assert store.get(session.session_id) is None


def test_login_return_path_rejects_open_redirect() -> None:
    store = LoginTransactionStore()
    for unsafe in ("https://evil.example", "//evil.example", "/auth/callback", "javascript:x"):
        with pytest.raises(BrowserOidcError, match="OIDC_RETURN_PATH_INVALID"):
            store.create(unsafe, "browser-binding")


def test_login_transaction_is_bound_to_initiating_browser() -> None:
    store = LoginTransactionStore(clock=lambda: 10.0)
    transaction = store.create("/cases", "browser-a")

    with pytest.raises(BrowserOidcError, match="OIDC_STATE_INVALID"):
        store.consume(transaction.state, "browser-b")

    assert store.consume(transaction.state, "browser-a") == transaction
