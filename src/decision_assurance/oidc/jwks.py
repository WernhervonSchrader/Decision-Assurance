from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import httpx
from jwt import PyJWK


class JwksResolutionError(ValueError):
    pass


class CachedJwksProvider:
    def __init__(
        self,
        *,
        issuer: str,
        jwks_uri: str,
        client: httpx.Client,
        cache_ttl_seconds: int = 300,
        maximum_keys: int = 20,
        allow_insecure_loopback: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ):
        def trusted_url(value: str) -> bool:
            parsed = urlsplit(value)
            return parsed.scheme == "https" or (
                allow_insecure_loopback
                and parsed.scheme == "http"
                and parsed.hostname in {"127.0.0.1", "::1", "localhost"}
            )

        if not trusted_url(issuer) or not trusted_url(jwks_uri):
            raise ValueError("OIDC_HTTPS_REQUIRED")
        if not 30 <= cache_ttl_seconds <= 86_400:
            raise ValueError("INVALID_JWKS_CACHE_TTL")
        if not 1 <= maximum_keys <= 100:
            raise ValueError("INVALID_JWKS_KEY_LIMIT")
        self._issuer = issuer
        self._jwks_uri = jwks_uri
        self._client = client
        self._cache_ttl_seconds = cache_ttl_seconds
        self._maximum_keys = maximum_keys
        self._clock = clock
        self._keys: dict[str, PyJWK] = {}
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def get(self, kid: str, algorithm: str) -> Any:
        if not kid or len(kid) > 256:
            raise JwksResolutionError("INVALID_KEY_ID")
        with self._lock:
            if self._clock() >= self._expires_at:
                self._refresh()
            key = self._keys.get(kid)
            if key is None:
                self._refresh()
                key = self._keys.get(kid)
            if key is None or key.algorithm_name != algorithm:
                raise JwksResolutionError("OIDC_KEY_NOT_FOUND")
            return key.key

    def _refresh(self) -> None:
        try:
            response = self._client.get(
                self._jwks_uri,
                headers={"Accept": "application/json"},
                timeout=5.0,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            raise JwksResolutionError("JWKS_UNAVAILABLE") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
            raise JwksResolutionError("INVALID_JWKS_DOCUMENT")
        raw_keys = payload["keys"]
        if not 1 <= len(raw_keys) <= self._maximum_keys:
            raise JwksResolutionError("INVALID_JWKS_KEY_COUNT")
        parsed: dict[str, PyJWK] = {}
        try:
            for raw in raw_keys:
                if not isinstance(raw, dict):
                    raise JwksResolutionError("INVALID_JWKS_KEY")
                # OIDC providers commonly publish encryption and signing keys in
                # one JWKS. Encryption keys are valid document members but must
                # never enter the verification-key cache.
                if raw.get("use", "sig") != "sig":
                    continue
                kid = raw.get("kid")
                if not isinstance(kid, str) or not kid or kid in parsed:
                    raise JwksResolutionError("INVALID_JWKS_KEY_ID")
                if raw.get("kty") not in {"RSA", "EC"}:
                    raise JwksResolutionError("INVALID_JWKS_KEY_USE")
                parsed[kid] = PyJWK.from_dict(raw)
        except (KeyError, TypeError, ValueError):
            raise JwksResolutionError("INVALID_JWKS_KEY") from None
        if not parsed:
            raise JwksResolutionError("INVALID_JWKS_KEY_COUNT")
        self._keys = parsed
        self._expires_at = self._clock() + self._cache_ttl_seconds
