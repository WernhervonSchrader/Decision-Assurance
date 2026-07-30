from datetime import datetime, timezone

import pytest

from decision_assurance.audit import payload_hash
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.tenancy import TenantContext
from decision_assurance.web_research.compiler import (
    ResearchEvidenceCompiler,
    SqliteDecisionEvidenceHandoff,
)
from decision_assurance.web_research.contracts import (
    ExtractedContent,
    ExtractionResponse,
    FreshnessPolicy,
    ResearchRequest,
    SearchResponse,
    SearchResult,
)
from decision_assurance.web_research.evidence_policy import EvidencePolicy
from decision_assurance.web_research.normalization import EvidenceNormalizer
from decision_assurance.web_research.orchestrator import ResearchOrchestrator, ResearchPolicy
from decision_assurance.web_research.providers.fakes import FakeContentExtractor, FakeSearchProvider
from decision_assurance.web_research.repository import SqliteResearchRepository
from decision_assurance.web_research.url_policy import PublicUrlPolicy

NOW = datetime(2026, 7, 29, tzinfo=timezone.utc)


class Resolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        del hostname
        return ("93.184.216.34",)


@pytest.mark.anyio
async def test_complete_fake_pipeline_is_semantically_idempotent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "pipeline.db"
    decisions = SqliteDecisionRepository(database)
    research = SqliteResearchRepository(database)
    decisions.initialize()
    research.initialize()
    document = __import__("json").loads(
        __import__("pathlib").Path("examples/decision-cases/low-risk-pass.json").read_text()
    )
    tenant = TenantContext("tenant-a")
    decisions.create_decision(tenant, document)

    search = FakeSearchProvider(
        SearchResponse(
            "fake-search",
            "v1",
            NOW.isoformat(),
            (
                SearchResult("https://one.example/rule", "One", "One", 1, NOW.isoformat()),
                SearchResult("https://two.example/rule", "Two", "Two", 2, NOW.isoformat()),
                SearchResult("https://one.example/rule#again", "Duplicate", "", 3),
            ),
        )
    )
    extractor = FakeContentExtractor(
        {
            url: ExtractionResponse(
                content=ExtractedContent(
                    f"{title}: " + "Authoritative content " * 30,
                    title,
                    url,
                    NOW.isoformat(),
                    "text/markdown",
                    200,
                    language,
                    "fake-extractor",
                    "v1",
                )
            )
            for url, title, language in (
                ("https://one.example/rule", "One", "de"),
                ("https://two.example/rule", "Two", "en"),
            )
        }
    )
    orchestrator = ResearchOrchestrator(
        search,
        extractor,
        research,
        PublicUrlPolicy(Resolver()),
        EvidenceNormalizer(max_content_bytes=100_000),
        EvidencePolicy(primary_domains=("one.example", "two.example")),
        ResearchEvidenceCompiler(),
        SqliteDecisionEvidenceHandoff(database),
        policy=ResearchPolicy(provider_budget=10),
        clock=lambda: NOW,
    )
    request = ResearchRequest(
        decision_file_id=document["decision_id"],
        claim_refs=(document["claims"][0]["id"],),
        query="Welche Regeln gelten?",
        locale="de-DE",
        preferred_languages=("de", "en"),
        max_search_results=3,
        max_sources_to_extract=2,
        freshness=FreshnessPolicy(365, True),
    )
    first = await orchestrator.execute(
        tenant, "actor-1", request, payload_hash(document), "correlation-1"
    )
    second = await orchestrator.execute(
        tenant, "actor-2", request, payload_hash(document), "correlation-2"
    )

    assert first.status.value == "COMPLETED"
    assert second.research_run_id == first.research_run_id
    assert len(search.calls) == 1
    assert len(extractor.calls) == 2
    assert first.provider_cost_units == 3
    assert len(first.evidence) == 2
    decision = decisions.get_decision(tenant, document["decision_id"])
    assert decision is not None
    attached = [item for item in decision["evidence"] if item["id"].startswith("research-")]
    assert {item["status"] for item in attached} == {"UNVERIFIED"}
