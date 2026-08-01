from __future__ import annotations

import base64
import hashlib
import hmac
import re
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit

import httpx
import jwt

from ..oidc.jwks import CachedJwksProvider
from .errors import BrowserOidcError
from .session import LoginTransaction, SensitiveToken

__all__ = ["BrowserOidcError", "OidcBrowserClient", "TokenSet"]
_PKCE_VERIFIER = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")


@dataclass(frozen=True, slots=True, repr=False)
class TokenSet:
    access_token: SensitiveToken
    expires_in: int

    def __repr__(self) -> str:
        return "TokenSet(**redacted**)"


class OidcBrowserClient:
    def __init__(
        self,
        *,
        issuer: str,
        client_id: str,
        authorization_endpoint: str,
        token_endpoint: str,
        redirect_uri: str,
        keys: CachedJwksProvider,
        http_client: httpx.Client,
        algorithms: tuple[str, ...] = ("RS256",),
    ):
        if not client_id.strip() or not algorithms:
            raise ValueError("INVALID_BROWSER_OIDC_CONFIGURATION")
        issuer_parts = urlsplit(issuer)
        for endpoint in (authorization_endpoint, token_endpoint, redirect_uri):
            parsed = urlsplit(endpoint)
            if parsed.scheme != "https" or not parsed.hostname:
                raise ValueError("BROWSER_OIDC_HTTPS_REQUIRED")
        if urlsplit(authorization_endpoint).hostname != issuer_parts.hostname:
            raise ValueError("BROWSER_OIDC_ISSUER_MISMATCH")
        if urlsplit(token_endpoint).hostname != issuer_parts.hostname:
            raise ValueError("BROWSER_OIDC_ISSUER_MISMATCH")
        self._issuer = issuer.rstrip("/")
        self._client_id = client_id
        self._authorization_endpoint = authorization_endpoint
        self._token_endpoint = token_endpoint
        self._redirect_uri = redirect_uri
        self._keys = keys
        self._http = http_client
        self._algorithms = algorithms

    def authorization_url(self, transaction: LoginTransaction) -> str:
        if not _PKCE_VERIFIER.fullmatch(transaction.code_verifier):
            raise BrowserOidcError("OIDC_PKCE_VERIFIER_INVALID")
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(transaction.code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": "openid da.api",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": transaction.state,
                "nonce": transaction.nonce,
            }
        )
        return f"{self._authorization_endpoint}?{query}"

    def exchange(self, code: str, transaction: LoginTransaction) -> TokenSet:
        if not code or len(code) > 4096:
            raise BrowserOidcError("OIDC_CODE_INVALID")
        if not _PKCE_VERIFIER.fullmatch(transaction.code_verifier):
            raise BrowserOidcError("OIDC_PKCE_VERIFIER_INVALID")
        try:
            response = self._http.post(
                self._token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "client_id": self._client_id,
                    "redirect_uri": self._redirect_uri,
                    "code": code,
                    "code_verifier": transaction.code_verifier,
                },
                headers={"Accept": "application/json"},
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            raise BrowserOidcError("OIDC_CODE_EXCHANGE_FAILED") from None
        if not isinstance(payload, dict):
            raise BrowserOidcError("OIDC_TOKEN_INVALID")
        access_token = payload.get("access_token")
        id_token = payload.get("id_token")
        expires_in = payload.get("expires_in")
        if (
            not isinstance(access_token, str)
            or not isinstance(id_token, str)
            or not isinstance(expires_in, int)
            or not 1 <= expires_in <= 3600
        ):
            raise BrowserOidcError("OIDC_TOKEN_INVALID")
        self._validate_id_token(id_token, transaction.nonce)
        return TokenSet(SensitiveToken(access_token), expires_in)

    def _validate_id_token(self, token: str, expected_nonce: str) -> None:
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            kid = header.get("kid")
            if algorithm not in self._algorithms or not isinstance(kid, str):
                raise BrowserOidcError("OIDC_ID_TOKEN_INVALID")
            key = self._keys.get(kid, str(algorithm))
            claims = jwt.decode(
                token,
                key,
                algorithms=list(self._algorithms),
                audience=self._client_id,
                issuer=self._issuer,
                options={
                    "require": ["iss", "aud", "sub", "iat", "exp", "nonce"],
                    "verify_signature": True,
                    "verify_aud": True,
                    "verify_iss": True,
                    "verify_exp": True,
                    "verify_iat": True,
                },
            )
            nonce = claims.get("nonce")
            if not isinstance(nonce, str) or not hmac.compare_digest(nonce, expected_nonce):
                raise BrowserOidcError("OIDC_NONCE_INVALID")
        except BrowserOidcError:
            raise
        except (jwt.PyJWTError, TypeError, ValueError):
            raise BrowserOidcError("OIDC_ID_TOKEN_INVALID") from None
