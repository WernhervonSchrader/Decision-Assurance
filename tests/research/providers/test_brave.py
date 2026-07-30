from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from decision_assurance.web_research.contracts import FreshnessPolicy, SearchQuery
from decision_assurance.web_research.providers.brave import BraveSearchProvider
from decision_assurance.web_research.providers.errors import ProviderRequestFailed

NOW = datetime(2026, 7, 29, tzinfo=timezone.utc)
SECRET = "brave-secret-value"  # noqa: S105 - verifies credentials are never exposed


def query(**overrides: Any) -> SearchQuery:
    values: dict[str, Any] = {
        "query": "current regulation",
        "locale": "en-US",
        "preferred_languages": ("en",),
        "count": 5,
        "freshness": FreshnessPolicy(30, True),
    }
    values.update(overrides)
    return SearchQuery(**values)


def provider(
    handler: httpx.MockTransport | None, *, api_key: str | None = SECRET
) -> BraveSearchProvider:
    client = httpx.AsyncClient(transport=handler) if handler else None
    return BraveSearchProvider(api_key=api_key, client=client, clock=lambda: NOW)


@pytest.mark.anyio
async def test_success_normalizes_discovery_and_ignores_additive_fields() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/res/v1/web/search"
        assert request.headers["X-Subscription-Token"] == SECRET
        assert request.url.params["count"] == "5"
        assert request.url.params["search_lang"] == "en"
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "url": "https://example.com/rule",
                            "title": "Rule",
                            "description": "Current rule",
                            "page_age": "2026-07-20T00:00:00Z",
                            "future_addition": {"ignored": True},
                        }
                    ],
                    "future_addition": True,
                },
                "future_addition": "ignored",
            },
            headers={"x-request-id": "request-secret-that-is-not-retained"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await BraveSearchProvider(api_key=SECRET, client=client, clock=lambda: NOW).search(
            query()
        )

    assert result.provider_id == "brave-search"
    assert result.provider_version == "web-search-v1"
    assert result.searched_at == NOW.isoformat()
    assert result.results[0].url == "https://example.com/rule"
    assert result.results[0].rank == 1
    assert result.results[0].published_at == "2026-07-20T00:00:00Z"


@pytest.mark.anyio
async def test_empty_results_are_valid() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"web": {"results": []}})
    )
    async with httpx.AsyncClient(transport=transport) as client:
        result = await BraveSearchProvider(api_key=SECRET, client=client).search(query())
    assert result.results == ()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({}, "PROVIDER_SCHEMA_INVALID"),
        ({"web": {"results": "wrong"}}, "PROVIDER_SCHEMA_INVALID"),
        ({"web": {"results": [{"url": 4, "title": "x"}]}}, "PROVIDER_SCHEMA_INVALID"),
    ],
)
async def test_schema_drift_fails_closed(payload: object, reason: str) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ProviderRequestFailed) as caught:
            await BraveSearchProvider(api_key=SECRET, client=client).search(query())
    assert caught.value.error.reason_code == reason
    assert not caught.value.error.retryable


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "reason", "retryable"),
    [
        (400, "SEARCH_REQUEST_REJECTED", False),
        (401, "PROVIDER_AUTHENTICATION_FAILED", False),
        (402, "PROVIDER_QUOTA_EXHAUSTED", False),
        (408, "SEARCH_TIMEOUT", True),
        (429, "PROVIDER_RATE_LIMITED", True),
        (500, "PROVIDER_UNAVAILABLE", True),
        (503, "PROVIDER_UNAVAILABLE", True),
    ],
)
async def test_http_failures_are_translated(status: int, reason: str, retryable: bool) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            status, json={"message": SECRET}, headers={"Retry-After": "3"}
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ProviderRequestFailed) as caught:
            await BraveSearchProvider(api_key=SECRET, client=client).search(query())
    assert caught.value.error.reason_code == reason
    assert caught.value.error.retryable is retryable
    assert caught.value.error.retry_after_seconds == (3.0 if status == 429 else None)
    assert SECRET not in str(caught.value)


@pytest.mark.anyio
async def test_timeout_is_controlled_and_not_retried_blindly() -> None:
    calls = 0

    def timeout(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout(SECRET, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(ProviderRequestFailed) as caught:
            await BraveSearchProvider(api_key=SECRET, client=client).search(query())
    assert caught.value.error.reason_code == "SEARCH_TIMEOUT"
    assert calls == 1
    assert SECRET not in str(caught.value)


@pytest.mark.anyio
async def test_missing_configuration_is_controlled_without_making_a_request() -> None:
    with pytest.raises(ProviderRequestFailed) as caught:
        await BraveSearchProvider(api_key=None).search(query())
    assert caught.value.error.reason_code == "PROVIDER_NOT_CONFIGURED"
    assert "None" not in str(caught.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalid",
    [
        query(query=""),
        query(query="word " * 51),
        query(query="x" * 401),
        query(count=0),
        query(count=21),
    ],
)
async def test_query_boundaries_fail_before_network(invalid: SearchQuery) -> None:
    with pytest.raises(ProviderRequestFailed) as caught:
        await BraveSearchProvider(api_key=SECRET).search(invalid)
    assert caught.value.error.reason_code == "INVALID_SEARCH_QUERY"
