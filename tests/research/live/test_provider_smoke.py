from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from decision_assurance.audit import payload_hash
from decision_assurance.production.config import load_config
from decision_assurance.production.contracts import EnvironmentProfile, SecretReference
from decision_assurance.production.egress import (
    EgressRequestContext,
    ResidencyEgressGuard,
    bind_egress_context,
)
from decision_assurance.production.secrets import FileSecretProvider, SecretResolutionError
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.tenancy import TenantContext
from decision_assurance.web_research.compiler import (
    ResearchEvidenceCompiler,
    SqliteDecisionEvidenceHandoff,
)
from decision_assurance.web_research.contracts import (
    ExtractionRequest,
    FreshnessPolicy,
    ResearchRequest,
    SearchQuery,
)
from decision_assurance.web_research.evidence_policy import EvidencePolicy
from decision_assurance.web_research.normalization import EvidenceNormalizer
from decision_assurance.web_research.orchestrator import ResearchOrchestrator, ResearchPolicy
from decision_assurance.web_research.providers.brave import BraveSearchProvider
from decision_assurance.web_research.providers.firecrawl import FirecrawlContentExtractor
from decision_assurance.web_research.repository import SqliteResearchRepository
from decision_assurance.web_research.url_policy import PublicUrlPolicy, SystemResolver

pytestmark = pytest.mark.live_provider
SECRET_DIRECTORY = Path(".secrets")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _secrets() -> tuple[str, str]:
    if os.getenv("DA_RUN_LIVE_PROVIDER_TESTS") != "1":
        pytest.skip("live provider tests require explicit opt-in")
    provider = FileSecretProvider(SECRET_DIRECTORY)
    try:
        brave = provider.resolve(SecretReference("BRAVE_API_KEY")).value
        firecrawl = provider.resolve(SecretReference("FIRECRAWL_API_KEY")).value
    except SecretResolutionError:
        pytest.skip("local provider credentials are unavailable")
    return brave, firecrawl


def _guard() -> ResidencyEgressGuard:
    config = load_config(
        Path("config/deployment/provider-development.example.json"),
        {"DA_PROFILE": "development"},
    )
    return ResidencyEgressGuard(
        lambda: config,
        expected_profile=EnvironmentProfile.DEVELOPMENT,
    )


def _context(correlation_id: str) -> EgressRequestContext:
    return EgressRequestContext(
        "live-provider-pilot",
        "local-smoke-operator",
        correlation_id,
        lambda event: None,
    )


def _report(*, status: str, duration: float, count: int, correlation_id: str) -> None:
    print(
        json.dumps(
            {
                "status": status,
                "http_result_class": "2xx",
                "duration_ms": round(duration * 1000, 1),
                "result_count": count,
                "correlation_id": correlation_id,
            },
            sort_keys=True,
        )
    )


@pytest.mark.anyio
async def test_live_brave_minimal_search() -> None:
    brave_key, _ = _secrets()
    correlation_id = "live-brave-smoke"
    started = time.monotonic()
    with bind_egress_context(_context(correlation_id)):
        response = await BraveSearchProvider(api_key=brave_key, egress_guard=_guard()).search(
            SearchQuery("site:example.com Example Domain", "en-US", ("en",), 3)
        )
    assert response.results
    _report(
        status="PASS",
        duration=time.monotonic() - started,
        count=len(response.results),
        correlation_id=correlation_id,
    )


@pytest.mark.anyio
async def test_live_firecrawl_minimal_scrape() -> None:
    _, firecrawl_key = _secrets()
    correlation_id = "live-firecrawl-smoke"
    started = time.monotonic()
    with bind_egress_context(_context(correlation_id)):
        response = await FirecrawlContentExtractor(
            api_key=firecrawl_key,
            url_policy=PublicUrlPolicy(SystemResolver()),
            egress_guard=_guard(),
        ).extract(ExtractionRequest("live-source", "https://example.com/", "en-US", 100_000, 0))
    assert response.error is None and response.content is not None
    _report(
        status="PASS",
        duration=time.monotonic() - started,
        count=1,
        correlation_id=correlation_id,
    )


@pytest.mark.anyio
async def test_live_combined_provider_to_evidence_pipeline(tmp_path: Path) -> None:
    brave_key, firecrawl_key = _secrets()
    correlation_id = "live-combined-smoke"
    database = tmp_path / "live-provider.db"
    decisions = SqliteDecisionRepository(database)
    research = SqliteResearchRepository(database)
    decisions.initialize()
    research.initialize()
    document = json.loads(Path("examples/decision-cases/low-risk-pass.json").read_text())
    tenant = TenantContext("live-provider-pilot")
    decisions.create_decision(tenant, document)
    url_policy = PublicUrlPolicy(SystemResolver())
    orchestrator = ResearchOrchestrator(
        BraveSearchProvider(api_key=brave_key, egress_guard=_guard()),
        FirecrawlContentExtractor(
            api_key=firecrawl_key,
            url_policy=url_policy,
            egress_guard=_guard(),
        ),
        research,
        url_policy,
        EvidenceNormalizer(max_content_bytes=100_000),
        EvidencePolicy(),
        ResearchEvidenceCompiler(),
        SqliteDecisionEvidenceHandoff(database),
        policy=ResearchPolicy(
            provider_budget=4,
            max_search_results=3,
            max_extractions=1,
            max_content_bytes=100_000,
        ),
        clock=lambda: datetime.now(timezone.utc),
    )
    request = ResearchRequest(
        document["decision_id"],
        (document["claims"][0]["id"],),
        "site:example.com Example Domain",
        "en-US",
        ("en",),
        3,
        1,
        freshness=FreshnessPolicy(3650, True),
    )
    started = time.monotonic()
    run = await orchestrator.execute(
        tenant,
        "local-smoke-operator",
        request,
        payload_hash(document),
        correlation_id,
    )
    assert run.snapshots and run.evidence
    _report(
        status="PASS",
        duration=time.monotonic() - started,
        count=len(run.evidence),
        correlation_id=correlation_id,
    )
