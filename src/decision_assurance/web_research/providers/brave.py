from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import NoReturn
from urllib.parse import urlsplit

import httpx

from ...production.egress import EgressRejected, ResidencyEgressGuard
from ..contracts import ProviderError, SearchQuery, SearchResponse, SearchResult
from .errors import ProviderRequestFailed

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BraveSearchProvider:
    """Discovery-only adapter for Brave Web Search API v1."""

    provider_id = "brave-search"
    provider_version = "web-search-v1"

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.search.brave.com",
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
        clock: Clock = _utc_now,
        egress_guard: ResidencyEgressGuard | None = None,
    ):
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("INVALID_BRAVE_BASE_URL")
        if not 0.1 <= timeout_seconds <= 120:
            raise ValueError("INVALID_BRAVE_TIMEOUT")
        self._api_key = api_key.strip() if api_key else None
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client
        self._clock = clock
        self._egress_guard = egress_guard or ResidencyEgressGuard(lambda: None)

    async def search(self, request: SearchQuery) -> SearchResponse:
        self._validate(request)
        if not self._api_key:
            self._fail("PROVIDER_NOT_CONFIGURED", False)
        params = {
            "q": request.query.strip(),
            "count": str(request.count),
            "search_lang": request.preferred_languages[0].split("-", 1)[0].casefold(),
            "ui_lang": request.locale,
            "freshness": self._freshness(request.freshness.maximum_age_days),
        }
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self._api_key,
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
                url=f"{self._base_url}/res/v1/web/search",
            )
            response = await client.get(
                request_url,
                params=params,
                headers=headers,
                timeout=self._timeout,
            )
        except httpx.TimeoutException:
            self._fail("SEARCH_TIMEOUT", True)
        except httpx.HTTPError:
            self._fail("PROVIDER_UNAVAILABLE", True)
        except EgressRejected as error:
            self._fail(error.reason_code, False)
        finally:
            if owns_client:
                await client.aclose()
        if response.status_code != 200:
            self._raise_for_status(response)
        return self._normalize(response)

    @classmethod
    def _validate(cls, request: SearchQuery) -> None:
        query = request.query.strip()
        if (
            not query
            or len(query) > 400
            or len(query.split()) > 50
            or not 1 <= request.count <= 20
            or not request.preferred_languages
        ):
            cls._fail("INVALID_SEARCH_QUERY", False)

    def _normalize(self, response: httpx.Response) -> SearchResponse:
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise TypeError
            web = payload["web"]
            if not isinstance(web, dict):
                raise TypeError
            raw_results = web["results"]
            if not isinstance(raw_results, list):
                raise TypeError
            results: list[SearchResult] = []
            for rank, raw in enumerate(raw_results, 1):
                if not isinstance(raw, dict):
                    raise TypeError
                url, title = raw.get("url"), raw.get("title")
                snippet = raw.get("description", "")
                published = raw.get("page_age")
                if (
                    not isinstance(url, str)
                    or not isinstance(title, str)
                    or not isinstance(snippet, str)
                    or (published is not None and not isinstance(published, str))
                ):
                    raise TypeError
                results.append(SearchResult(url, title, snippet, rank, published))
        except (KeyError, TypeError, ValueError):
            self._fail("PROVIDER_SCHEMA_INVALID", False)
        return SearchResponse(
            self.provider_id,
            self.provider_version,
            self._clock().astimezone(timezone.utc).isoformat(),
            tuple(results),
        )

    @classmethod
    def _raise_for_status(cls, response: httpx.Response) -> None:
        status = response.status_code
        mapping = {
            400: ("SEARCH_REQUEST_REJECTED", False),
            401: ("PROVIDER_AUTHENTICATION_FAILED", False),
            402: ("PROVIDER_QUOTA_EXHAUSTED", False),
            408: ("SEARCH_TIMEOUT", True),
            429: ("PROVIDER_RATE_LIMITED", True),
        }
        reason, retryable = mapping.get(
            status,
            ("PROVIDER_UNAVAILABLE", True)
            if 500 <= status <= 599
            else ("SEARCH_PROVIDER_ERROR", False),
        )
        retry_after = cls._retry_after(response) if status == 429 else None
        cls._fail(reason, retryable, status, retry_after)

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        try:
            value = float(response.headers.get("Retry-After", ""))
        except ValueError:
            return None
        return min(value, 60.0) if value >= 0 else None

    @staticmethod
    def _freshness(maximum_age_days: int) -> str:
        if maximum_age_days <= 1:
            return "pd"
        if maximum_age_days <= 7:
            return "pw"
        if maximum_age_days <= 31:
            return "pm"
        return "py"

    @classmethod
    def _fail(
        cls,
        reason_code: str,
        retryable: bool,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> NoReturn:
        raise ProviderRequestFailed(
            ProviderError(
                cls.provider_id,
                reason_code,
                retryable,
                status_code,
                retry_after_seconds,
            )
        )
