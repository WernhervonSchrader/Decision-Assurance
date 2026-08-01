from __future__ import annotations

import httpx

from .errors import BrowserOidcError
from .session import SensitiveToken


class PilotApiError(RuntimeError):
    pass


class HttpPilotApiClient:
    def __init__(self, base_url: str, client: httpx.Client):
        self._base_url = base_url.rstrip("/")
        self._client = client

    def session(self, token: SensitiveToken, correlation_id: str) -> dict[str, object]:
        response = self.request(
            token,
            "GET",
            "/v1/session",
            query="",
            body=b"",
            locale="en",
            correlation_id=correlation_id,
            idempotency_key=None,
        )
        if response.status_code != 200:
            raise BrowserOidcError("OIDC_API_IDENTITY_REJECTED")
        try:
            value = response.json()
        except ValueError:
            raise BrowserOidcError("OIDC_API_IDENTITY_REJECTED") from None
        if not isinstance(value, dict):
            raise BrowserOidcError("OIDC_API_IDENTITY_REJECTED")
        return value

    def request(
        self,
        token: SensitiveToken,
        method: str,
        path: str,
        *,
        query: str,
        body: bytes,
        locale: str,
        correlation_id: str,
        idempotency_key: str | None,
    ) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {token.value}",
            "Accept-Language": locale,
            "X-Correlation-ID": correlation_id,
            "Accept": "application/json, application/zip",
        }
        if body:
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            return self._client.request(
                method,
                f"{self._base_url}{path}" + (f"?{query}" if query else ""),
                headers=headers,
                content=body,
                follow_redirects=False,
                timeout=15.0,
            )
        except httpx.HTTPError:
            raise PilotApiError("PILOT_API_UNAVAILABLE") from None

    def __repr__(self) -> str:
        return "HttpPilotApiClient(**redacted**)"
