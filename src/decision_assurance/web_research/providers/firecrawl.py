from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from ...production.egress import EgressRejected, ResidencyEgressGuard
from ..contracts import (
    ExtractedContent,
    ExtractionRequest,
    ExtractionResponse,
    ProviderError,
)
from ..url_policy import PublicUrlPolicy, UrlPolicyRejected

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FirecrawlContentExtractor:
    """Extraction-only adapter for Firecrawl Scrape API v2."""

    provider_id = "firecrawl"
    provider_version = "scrape-v2"

    def __init__(
        self,
        *,
        api_key: str | None,
        url_policy: PublicUrlPolicy,
        base_url: str = "https://api.firecrawl.dev",
        timeout_seconds: float = 20.0,
        max_content_bytes: int = 1_000_000,
        client: httpx.AsyncClient | None = None,
        clock: Clock = _utc_now,
        egress_guard: ResidencyEgressGuard | None = None,
    ):
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("INVALID_FIRECRAWL_BASE_URL")
        if not 0.1 <= timeout_seconds <= 120:
            raise ValueError("INVALID_FIRECRAWL_TIMEOUT")
        if not 1_000 <= max_content_bytes <= 10_000_000:
            raise ValueError("INVALID_CONTENT_LIMIT")
        self._api_key = api_key.strip() if api_key else None
        self._url_policy = url_policy
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._max_content_bytes = max_content_bytes
        self._client = client
        self._clock = clock
        self._egress_guard = egress_guard or ResidencyEgressGuard(lambda: None)

    async def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        if not self._api_key:
            return self._error("PROVIDER_NOT_CONFIGURED", False)
        try:
            safe_url = self._url_policy.validate(request.url)
        except UrlPolicyRejected as error:
            return self._error(str(error), False)
        body = {
            "url": safe_url.canonical_url,
            "formats": ["markdown"],
            "onlyMainContent": True,
            "skipTlsVerification": False,
        }
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=False,
        )
        try:
            request_url = self._egress_guard.authorize_current(
                provider=self.provider_id,
                connector=self.provider_version,
                url=f"{self._base_url}/v2/scrape",
            )
            response = await client.post(
                request_url,
                json=body,
                headers=headers,
                timeout=self._timeout,
            )
        except httpx.TimeoutException:
            return self._error("EXTRACTION_TIMEOUT", True)
        except httpx.HTTPError:
            return self._error("PROVIDER_UNAVAILABLE", True)
        except EgressRejected as error:
            return self._error(error.reason_code, False)
        finally:
            if owns_client:
                await client.aclose()
        if response.status_code != 200:
            return self._error_for_status(response)
        return self._normalize(response, request, safe_url.domain)

    def _normalize(
        self, response: httpx.Response, request: ExtractionRequest, requested_domain: str
    ) -> ExtractionResponse:
        try:
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("success") is not True:
                raise TypeError
            data = payload["data"]
            if not isinstance(data, dict):
                raise TypeError
            markdown = data["markdown"]
            metadata = data["metadata"]
            if not isinstance(markdown, str) or not isinstance(metadata, dict):
                raise TypeError
            canonical_url = metadata["sourceURL"]
            mime_type = metadata["contentType"]
            http_status = metadata["statusCode"]
            title = metadata.get("title", "")
            language = metadata.get("language", request.locale.split("-", 1)[0])
            if (
                not isinstance(canonical_url, str)
                or not isinstance(mime_type, str)
                or not isinstance(http_status, int)
                or isinstance(http_status, bool)
                or not isinstance(title, str)
                or not isinstance(language, str)
            ):
                raise TypeError
        except (KeyError, TypeError, ValueError):
            return self._error("PROVIDER_SCHEMA_INVALID", False)
        if not markdown.strip():
            return self._error("EMPTY_EXTRACTED_CONTENT", False)
        effective_limit = min(self._max_content_bytes, request.max_content_bytes)
        if len(markdown.encode("utf-8")) > effective_limit:
            return self._error("CONTENT_TOO_LARGE", False)
        if http_status != 200:
            return self._error("EXTRACTION_ERROR_PAGE", False, http_status)
        if mime_type.casefold().split(";", 1)[0] not in {
            "text/markdown",
            "text/plain",
            "text/html",
        }:
            return self._error("MIME_TYPE_UNSUPPORTED", False)
        try:
            final_url = self._url_policy.validate(canonical_url)
        except UrlPolicyRejected as error:
            return self._error(str(error), False)
        if final_url.domain != requested_domain:
            return self._error("CROSS_DOMAIN_REDIRECT", False)
        return ExtractionResponse(
            content=ExtractedContent(
                markdown,
                title,
                final_url.canonical_url,
                self._clock().astimezone(timezone.utc).isoformat(),
                mime_type,
                http_status,
                language,
                self.provider_id,
                self.provider_version,
                response.headers.get("x-request-id"),
            )
        )

    def _error_for_status(self, response: httpx.Response) -> ExtractionResponse:
        status = response.status_code
        mapping = {
            400: ("EXTRACTION_REQUEST_REJECTED", False),
            401: ("PROVIDER_AUTHENTICATION_FAILED", False),
            402: ("PROVIDER_QUOTA_EXHAUSTED", False),
            408: ("EXTRACTION_TIMEOUT", True),
            413: ("CONTENT_TOO_LARGE", False),
            429: ("PROVIDER_RATE_LIMITED", True),
        }
        reason, retryable = mapping.get(
            status,
            ("PROVIDER_UNAVAILABLE", True)
            if status in {500, 502, 503, 504}
            else ("EXTRACTION_PROVIDER_ERROR", False),
        )
        retry_after = self._retry_after(response) if status == 429 else None
        return self._error(reason, retryable, status, retry_after)

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        try:
            value = float(response.headers.get("Retry-After", ""))
        except ValueError:
            return None
        return min(value, 60.0) if value >= 0 else None

    @classmethod
    def _error(
        cls,
        reason_code: str,
        retryable: bool,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> ExtractionResponse:
        return ExtractionResponse(
            error=ProviderError(
                cls.provider_id,
                reason_code,
                retryable,
                status_code,
                retry_after_seconds,
            )
        )
