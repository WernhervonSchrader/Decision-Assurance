from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

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
    ProviderError,
    ResearchRequest,
    ResearchStatus,
    SearchResponse,
    SearchResult,
)
from decision_assurance.web_research.evidence_policy import EvidencePolicy
from decision_assurance.web_research.normalization import EvidenceNormalizer
from decision_assurance.web_research.orchestrator import ResearchOrchestrator, ResearchPolicy
from decision_assurance.web_research.providers.errors import ProviderRequestFailed
from decision_assurance.web_research.repository import SqliteResearchRepository
from decision_assurance.web_research.url_policy import PublicUrlPolicy

NOW = datetime(2026, 7, 29, tzinfo=timezone.utc)


class Resolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        del hostname
        return ("93.184.216.34",)


class Search:
    provider_id = "fake-brave"

    def __init__(self, response: SearchResponse | ProviderError):
        self.response = response
        self.calls = 0

    async def search(self, request):  # type: ignore[no-untyped-def]
        del request
        self.calls += 1
        if isinstance(self.response, ProviderError):
            raise ProviderRequestFailed(self.response)
        return self.response


class SequencedSearch:
    provider_id = "fake-brave"

    def __init__(self, responses: list[SearchResponse | ProviderError]):
        self.responses = responses
        self.calls = 0

    async def search(self, request):  # type: ignore[no-untyped-def]
        del request
        value = self.responses.pop(0)
        self.calls += 1
        if isinstance(value, ProviderError):
            raise ProviderRequestFailed(value)
        return value


class SequencedExtractor:
    provider_id = "fake-firecrawl"

    def __init__(self, responses: dict[str, list[ExtractionResponse]]):
        self.responses = responses
        self.calls: list[str] = []

    async def extract(self, request):  # type: ignore[no-untyped-def]
        self.calls.append(request.url)
        values = self.responses[request.url]
        return values.pop(0) if len(values) > 1 else values[0]


def response_for(url: str, text: str) -> ExtractionResponse:
    return ExtractionResponse(
        content=ExtractedContent(
            text,
            "Rule",
            url,
            NOW.isoformat(),
            "text/markdown",
            200,
            "en",
            "fake-firecrawl",
            "v1",
        )
    )


def setup(tmp_path, search, extractor, *, budget: int = 10):  # type: ignore[no-untyped-def]
    database = tmp_path / "orchestration.db"
    decisions = SqliteDecisionRepository(database)
    repository = SqliteResearchRepository(database)
    decisions.initialize()
    repository.initialize()
    document = json.loads(Path("examples/decision-cases/low-risk-pass.json").read_text())
    tenant = TenantContext("tenant-a")
    decisions.create_decision(tenant, document)
    orchestrator = ResearchOrchestrator(
        search,
        extractor,
        repository,
        PublicUrlPolicy(Resolver()),
        EvidenceNormalizer(max_content_bytes=100_000),
        EvidencePolicy(primary_domains=("one.example", "two.example")),
        ResearchEvidenceCompiler(),
        SqliteDecisionEvidenceHandoff(database),
        policy=ResearchPolicy(provider_budget=budget, max_attempts_per_operation=2),
        clock=lambda: NOW,
    )
    request = ResearchRequest(
        document["decision_id"],
        (document["claims"][0]["id"],),
        "current rules",
        "en-US",
        ("en",),
        2,
        2,
        freshness=FreshnessPolicy(365, True),
    )
    return tenant, document, decisions, repository, orchestrator, request


def discovery() -> SearchResponse:
    return SearchResponse(
        "fake-brave",
        "v1",
        NOW.isoformat(),
        (
            SearchResult("https://one.example/rule", "One", "", 1, NOW.isoformat()),
            SearchResult("https://two.example/rule", "Two", "", 2, NOW.isoformat()),
        ),
    )


@pytest.mark.anyio
async def test_partial_retry_only_reprocesses_failed_source_and_converges(tmp_path) -> None:  # type: ignore[no-untyped-def]
    search = Search(discovery())
    extractor = SequencedExtractor(
        {
            "https://one.example/rule": [response_for("https://one.example/rule", "One " * 100)],
            "https://two.example/rule": [
                ExtractionResponse(
                    error=ProviderError("fake-firecrawl", "EXTRACTION_TIMEOUT", True)
                ),
                response_for("https://two.example/rule", "Two " * 100),
            ],
        }
    )
    tenant, document, decisions, repository, orchestrator, request = setup(
        tmp_path, search, extractor
    )

    first = await orchestrator.execute(
        tenant, "actor-1", request, payload_hash(document), "correlation-create"
    )
    retried = await orchestrator.retry(
        tenant, "actor-2", first.research_run_id, "correlation-retry"
    )

    assert first.status is ResearchStatus.PARTIALLY_COMPLETED
    assert retried.status is ResearchStatus.COMPLETED
    assert search.calls == 1
    assert extractor.calls == [
        "https://one.example/rule",
        "https://two.example/rule",
        "https://two.example/rule",
    ]
    assert retried.provider_cost_units == 4
    assert len(retried.evidence) == 2
    assert len({item.evidence_id for item in retried.evidence}) == 2
    assert len({item.event_id for item in retried.audit_events}) == len(retried.audit_events)
    stored = repository.get(tenant, retried.research_run_id)
    assert stored is not None and stored.status is ResearchStatus.COMPLETED
    decision = decisions.get_decision(tenant, document["decision_id"])
    assert decision is not None
    attached = [item for item in decision["evidence"] if item["id"].startswith("research-")]
    assert len(attached) == 2
    assert {item["status"] for item in attached} == {"UNVERIFIED"}


@pytest.mark.anyio
async def test_search_provider_failure_is_persisted_without_exception_details(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider_error = ProviderError("fake-brave", "PROVIDER_NOT_CONFIGURED", False)
    search = Search(provider_error)
    tenant, document, _, repository, orchestrator, request = setup(
        tmp_path, search, SequencedExtractor({})
    )
    run = await orchestrator.execute(
        tenant, "actor-1", request, payload_hash(document), "correlation-create"
    )
    assert run.status is ResearchStatus.FAILED
    assert len(run.errors) == 1
    assert run.errors[0].reason_code == "PROVIDER_NOT_CONFIGURED"
    assert repository.get(tenant, run.research_run_id) is not None


@pytest.mark.anyio
async def test_failed_search_can_be_retried_once_without_repeating_success(tmp_path) -> None:  # type: ignore[no-untyped-def]
    search = SequencedSearch([ProviderError("fake-brave", "SEARCH_TIMEOUT", True), discovery()])
    extractor = SequencedExtractor(
        {
            "https://one.example/rule": [response_for("https://one.example/rule", "One " * 100)],
            "https://two.example/rule": [response_for("https://two.example/rule", "Two " * 100)],
        }
    )
    tenant, document, _, _, orchestrator, request = setup(tmp_path, search, extractor)
    failed = await orchestrator.execute(
        tenant, "actor-1", request, payload_hash(document), "correlation-create"
    )
    completed = await orchestrator.retry(
        tenant, "actor-2", failed.research_run_id, "correlation-retry"
    )
    assert failed.status is ResearchStatus.FAILED
    assert completed.status is ResearchStatus.COMPLETED
    assert search.calls == 2
    assert completed.provider_cost_units == 4


@pytest.mark.anyio
async def test_budget_exhaustion_is_partial_and_never_overcharges(tmp_path) -> None:  # type: ignore[no-untyped-def]
    search = Search(discovery())
    extractor = SequencedExtractor(
        {
            "https://one.example/rule": [response_for("https://one.example/rule", "One " * 100)],
            "https://two.example/rule": [response_for("https://two.example/rule", "Two " * 100)],
        }
    )
    tenant, document, _, _, orchestrator, request = setup(tmp_path, search, extractor, budget=2)
    run = await orchestrator.execute(
        tenant, "actor-1", request, payload_hash(document), "correlation-create"
    )
    assert run.status is ResearchStatus.PARTIALLY_COMPLETED
    assert run.provider_cost_units == 2
    assert extractor.calls == ["https://one.example/rule"]
    assert any(item.reason_code == "BUDGET_EXCEEDED" for item in run.errors)


@pytest.mark.anyio
async def test_cancel_is_idempotent_and_terminal_runs_cannot_be_cancelled(tmp_path) -> None:  # type: ignore[no-untyped-def]
    search = Search(ProviderError("fake-brave", "PROVIDER_NOT_CONFIGURED", False))
    tenant, document, _, _, orchestrator, request = setup(tmp_path, search, SequencedExtractor({}))
    failed = await orchestrator.execute(
        tenant, "actor-1", request, payload_hash(document), "correlation-create"
    )
    cancelled = orchestrator.cancel(tenant, "actor-2", failed.research_run_id, "cancel-1")
    replay = orchestrator.cancel(tenant, "actor-2", failed.research_run_id, "cancel-1")
    assert cancelled.status is ResearchStatus.CANCELLED
    assert len(replay.audit_events) == len(cancelled.audit_events)
    with pytest.raises(ValueError, match="RESEARCH_TRANSITION_NOT_ALLOWED"):
        await orchestrator.retry(tenant, "actor-2", failed.research_run_id, "retry-after-cancel")
