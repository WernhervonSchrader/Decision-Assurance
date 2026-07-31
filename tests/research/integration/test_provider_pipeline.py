from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from decision_assurance.audit import payload_hash
from decision_assurance.production.config import load_config
from decision_assurance.production.contracts import EnvironmentProfile
from decision_assurance.production.egress import ResidencyEgressGuard
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.tenancy import TenantContext
from decision_assurance.web_research.compiler import (
    ResearchEvidenceCompiler,
    SqliteDecisionEvidenceHandoff,
)
from decision_assurance.web_research.contracts import FreshnessPolicy, ResearchRequest
from decision_assurance.web_research.evidence_policy import EvidencePolicy
from decision_assurance.web_research.normalization import EvidenceNormalizer
from decision_assurance.web_research.orchestrator import ResearchOrchestrator, ResearchPolicy
from decision_assurance.web_research.providers.firecrawl import FirecrawlContentExtractor
from decision_assurance.web_research.providers.openai_web_search import OpenAIWebSearchProvider
from decision_assurance.web_research.repository import SqliteResearchRepository
from decision_assurance.web_research.url_policy import PublicUrlPolicy

NOW = datetime(2026, 7, 31, tzinfo=timezone.utc)


class Resolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        del hostname
        return ("93.184.216.34",)


@pytest.mark.anyio
async def test_openai_to_firecrawl_to_evidence_uses_guard_and_preserves_provenance(
    tmp_path: Path,
) -> None:
    openai_calls = 0
    firecrawl_calls = 0

    def openai_handler(request: httpx.Request) -> httpx.Response:
        nonlocal openai_calls
        openai_calls += 1
        return httpx.Response(
            200,
            json={
                "id": "resp-provider-pipeline",
                "output": [
                    {
                        "type": "web_search_call",
                        "action": {
                            "type": "search",
                            "sources": [{"type": "url", "url": "https://one.example/rule"}],
                        },
                    },
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Official rule",
                                "annotations": [
                                    {
                                        "type": "url_citation",
                                        "start_index": 0,
                                        "end_index": 13,
                                        "url": "https://one.example/rule#section",
                                        "title": "Rule",
                                    }
                                ],
                            }
                        ],
                    },
                ],
            },
        )

    def firecrawl_handler(request: httpx.Request) -> httpx.Response:
        nonlocal firecrawl_calls
        firecrawl_calls += 1
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "markdown": "Authoritative regulatory content. " * 30,
                    "metadata": {
                        "title": "Rule",
                        "sourceURL": "https://one.example/rule",
                        "statusCode": 200,
                        "contentType": "text/markdown",
                        "language": "en",
                    },
                },
            },
            headers={"x-request-id": "firecrawl-request-1"},
        )

    config = load_config(
        Path("config/deployment/provider-development.example.json"),
        {"DA_PROFILE": "development"},
    )
    guard = ResidencyEgressGuard(
        lambda: config,
        clock=lambda: NOW,
        expected_profile=EnvironmentProfile.DEVELOPMENT,
    )
    database = tmp_path / "provider-pipeline.db"
    decisions = SqliteDecisionRepository(database)
    research = SqliteResearchRepository(database)
    decisions.initialize()
    research.initialize()
    document = json.loads(Path("examples/decision-cases/low-risk-pass.json").read_text())
    tenant = TenantContext("tenant-provider-pilot")
    decisions.create_decision(tenant, document)
    url_policy = PublicUrlPolicy(Resolver())

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(openai_handler)) as openai_client,
        httpx.AsyncClient(transport=httpx.MockTransport(firecrawl_handler)) as firecrawl_client,
    ):
        orchestrator = ResearchOrchestrator(
            OpenAIWebSearchProvider(
                api_key="openai-test-key",  # noqa: S106
                client=openai_client,
                clock=lambda: NOW,
                egress_guard=guard,
            ),
            FirecrawlContentExtractor(
                api_key="firecrawl-test-key",  # noqa: S106
                url_policy=url_policy,
                client=firecrawl_client,
                clock=lambda: NOW,
                egress_guard=guard,
            ),
            research,
            url_policy,
            EvidenceNormalizer(max_content_bytes=100_000),
            EvidencePolicy(primary_domains=("one.example",)),
            ResearchEvidenceCompiler(),
            SqliteDecisionEvidenceHandoff(database),
            policy=ResearchPolicy(provider_budget=10, max_search_results=2, max_extractions=2),
            clock=lambda: NOW,
        )
        request = ResearchRequest(
            document["decision_id"],
            (document["claims"][0]["id"],),
            "current regulation",
            "en-US",
            ("en",),
            2,
            2,
            freshness=FreshnessPolicy(365, True),
        )
        run = await orchestrator.execute(
            tenant, "actor-pilot", request, payload_hash(document), "corr-provider-pipeline"
        )

    assert run.status.value == "COMPLETED"
    assert openai_calls == 1 and firecrawl_calls == 1
    assert len(run.sources) == len(run.snapshots) == len(run.evidence) == 1
    source, snapshot, evidence = run.sources[0], run.snapshots[0], run.evidence[0]
    assert source.canonical_url == snapshot.canonical_url == "https://one.example/rule"
    assert source.published_at is None
    assert source.artifact_type == "SELECTED_SOURCE"
    assert snapshot.artifact_type == "FETCHED_CONTENT"
    assert evidence.artifact_type == "DERIVED_CLAIM"
    assert evidence.content_hash == snapshot.content_hash
    assert evidence.provenance.search_provider == "openai-web-search"
    assert evidence.provenance.content_provider == "firecrawl"
    assert evidence.source_id == source.source_id
    egress_events = [event for event in run.audit_events if event.decision == "ALLOWED"]
    assert {event.reason_codes for event in egress_events} == {("EGRESS_ALLOWED_DEVELOPMENT",)}
    assert {event.connector for event in egress_events} == {
        "responses-web-search-v1",
        "scrape-v2",
    }
    stored = research.get(tenant, run.research_run_id)
    assert stored is not None
    assert stored.search_summary == "Official rule"
    assert stored.search_provider_request_id == "resp-provider-pipeline"
    assert stored.sources[0] == source
    assert stored.snapshots[0].content_hash == snapshot.content_hash
    assert stored.evidence[0].provenance == evidence.provenance
    assert research.get(TenantContext("different-tenant"), run.research_run_id) is None
