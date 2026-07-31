from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from decision_assurance.web_research.contracts import FreshnessPolicy, SearchQuery
from decision_assurance.web_research.providers.errors import ProviderRequestFailed
from decision_assurance.web_research.providers.openai_web_search import OpenAIWebSearchProvider
from tests.research.providers.egress_support import ALLOW_EGRESS

NOW = datetime(2026, 7, 31, tzinfo=timezone.utc)
SECRET = "openai-secret-canary"  # noqa: S105


def query(**overrides: Any) -> SearchQuery:
    values: dict[str, Any] = {
        "query": "current regulation",
        "locale": "en-US",
        "preferred_languages": ("en",),
        "count": 5,
        "freshness": FreshnessPolicy(30, True),
        "allowed_domains": ("regulator.example",),
        "blocked_domains": ("blocked.example",),
    }
    values.update(overrides)
    return SearchQuery(**values)


def success_payload() -> dict[str, Any]:
    return {
        "id": "resp-safe-id",
        "output": [
            {
                "type": "web_search_call",
                "id": "ws-open-page-safe-id",
                "status": "completed",
                "action": {"type": "open_page", "url": "https://regulator.example/rule"},
            },
            {
                "type": "web_search_call",
                "id": "ws-safe-id",
                "status": "completed",
                "action": {
                    "type": "search",
                    "queries": ["current regulation"],
                    "sources": [
                        {
                            "type": "url",
                            "url": "https://consulted.example/background",
                            "published_date": "2026-07-29",
                        },
                        {"type": "url", "url": "https://regulator.example/rule"},
                    ],
                },
            },
            {
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "The current rule requires documented review.",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "start_index": 0,
                                "end_index": 16,
                                "url": "https://regulator.example/rule",
                                "title": "Current rule",
                            }
                        ],
                    }
                ],
            },
        ],
    }


def provider(
    handler: httpx.MockTransport | None, *, api_key: str | None = SECRET
) -> OpenAIWebSearchProvider:
    client = httpx.AsyncClient(transport=handler) if handler else None
    return OpenAIWebSearchProvider(
        api_key=api_key,
        client=client,
        clock=lambda: NOW,
        egress_guard=ALLOW_EGRESS,
    )


@pytest.mark.anyio
async def test_success_uses_responses_web_search_and_preserves_cited_and_consulted_sources() -> (
    None
):
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/responses"
        assert request.headers["Authorization"] == f"Bearer {SECRET}"
        payload = json.loads(request.content)
        assert payload["model"] == "gpt-5.6"
        assert payload["tools"] == [
            {
                "type": "web_search",
                "filters": {
                    "allowed_domains": ["regulator.example"],
                    "blocked_domains": ["blocked.example"],
                },
            }
        ]
        assert payload["tool_choice"] == "auto"
        assert payload["include"] == ["web_search_call.action.sources"]
        assert "untrusted" in payload["input"].casefold()
        assert SECRET not in request.content.decode()
        return httpx.Response(200, json=success_payload())

    response = await provider(httpx.MockTransport(handle)).search(query())

    assert response.provider_id == "openai-web-search"
    assert response.provider_version == "responses-web-search-v1"
    assert response.provider_request_id == "resp-safe-id"
    assert response.summary == "The current rule requires documented review."
    assert [(item.rank, item.citation_kind, item.url) for item in response.results] == [
        (1, "CITED", "https://regulator.example/rule"),
        (2, "CONSULTED", "https://consulted.example/background"),
    ]
    assert response.results[0].title == "Current rule"
    assert response.results[0].artifact_type == "SEARCH_RESULT"
    assert response.results[1].published_at == "2026-07-29"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"id": "resp", "output": "wrong"},
        {"id": "resp", "output": [{"type": "message", "content": []}]},
        {
            "id": "resp",
            "output": [
                {"type": "web_search_call", "status": "completed", "action": {"type": "search"}}
            ],
        },
        {
            "id": "resp",
            "output": [
                {
                    "type": "web_search_call",
                    "action": {"type": "search", "sources": []},
                },
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "x" * 32_769, "annotations": []}],
                },
            ],
        },
    ],
)
async def test_schema_drift_fails_closed(payload: object) -> None:
    with pytest.raises(ProviderRequestFailed, match="PROVIDER_SCHEMA_INVALID"):
        await provider(
            httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
        ).search(query())


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "reason", "retryable"),
    [
        (400, "SEARCH_REQUEST_REJECTED", False),
        (401, "PROVIDER_AUTHENTICATION_FAILED", False),
        (403, "PROVIDER_AUTHORIZATION_FAILED", False),
        (404, "SEARCH_ENDPOINT_NOT_FOUND", False),
        (408, "SEARCH_TIMEOUT", True),
        (429, "PROVIDER_RATE_LIMITED", True),
        (500, "PROVIDER_UNAVAILABLE", True),
        (503, "PROVIDER_UNAVAILABLE", True),
    ],
)
async def test_http_failures_are_secret_free_and_stable(
    status: int, reason: str, retryable: bool
) -> None:
    with pytest.raises(ProviderRequestFailed) as caught:
        await provider(
            httpx.MockTransport(
                lambda request: httpx.Response(
                    status, json={"error": SECRET}, headers={"Retry-After": "3"}
                )
            )
        ).search(query())
    assert caught.value.error.reason_code == reason
    assert caught.value.error.retryable is retryable
    assert caught.value.error.retry_after_seconds == (3.0 if status == 429 else None)
    assert SECRET not in str(caught.value)


@pytest.mark.anyio
async def test_timeout_is_controlled_without_blind_retry() -> None:
    calls = 0

    def timeout(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout(SECRET, request=request)

    with pytest.raises(ProviderRequestFailed, match="SEARCH_TIMEOUT"):
        await provider(httpx.MockTransport(timeout)).search(query())
    assert calls == 1


@pytest.mark.anyio
async def test_missing_key_disables_only_openai_search_before_network() -> None:
    with pytest.raises(ProviderRequestFailed, match="PROVIDER_NOT_CONFIGURED"):
        await provider(None, api_key=None).search(query())
