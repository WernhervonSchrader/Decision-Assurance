from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from decision_assurance.api.app import create_app
from decision_assurance.intake.contracts import PolicyContext
from decision_assurance.intake.postgresql_repository import PostgresIntakeRepository
from decision_assurance.intake.verification import InMemoryPolicyRegistry
from decision_assurance.jobs.postgresql import PostgresJobRepository
from decision_assurance.jobs.worker import ResearchWorker
from decision_assurance.observability.logging import JsonEventLogger
from decision_assurance.observability.metrics import InMemoryMetrics
from decision_assurance.oidc.authenticator import OidcAuthenticator
from decision_assurance.oidc.jwks import CachedJwksProvider
from decision_assurance.persistence.postgresql import (
    PostgresConnectionProvider,
    PostgresMigrationRunner,
    PostgresSettings,
)
from decision_assurance.production.contracts import OidcPolicy, SecretValue
from decision_assurance.repositories.postgresql import PostgresDecisionRepository
from decision_assurance.tenancy import TenantContext
from decision_assurance.web_research.compiler import (
    PostgresDecisionEvidenceHandoff,
    ResearchEvidenceCompiler,
)
from decision_assurance.web_research.contracts import (
    ExtractedContent,
    ExtractionResponse,
    ResearchStatus,
    SearchResponse,
    SearchResult,
)
from decision_assurance.web_research.evidence_policy import EvidencePolicy
from decision_assurance.web_research.normalization import EvidenceNormalizer
from decision_assurance.web_research.orchestrator import ResearchOrchestrator, ResearchPolicy
from decision_assurance.web_research.postgresql_repository import PostgresResearchRepository
from decision_assurance.web_research.providers.fakes import (
    FakeContentExtractor,
    FakeSearchProvider,
)
from decision_assurance.web_research.service import ResearchSubmissionService
from decision_assurance.web_research.url_policy import PublicUrlPolicy

ROOT = Path(__file__).parents[3]
MIGRATIONS = ROOT / "migrations" / "postgresql"
FIXTURES = ROOT / "tests" / "production" / "fixtures"
ISSUER = "https://pilot-identity.example.test"
AUDIENCE = "decision-assurance-pilot"
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
TENANTS = ("pilot-tenant-a", "pilot-tenant-b")
pytestmark = pytest.mark.postgresql


class Resolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        assert hostname == "pilot.example"
        return ("93.184.216.34",)


@pytest.fixture(scope="module")
def postgres_dsn() -> str:
    value = os.getenv("DA_TEST_POSTGRES_DSN")
    if not value:
        if os.getenv("CI"):
            pytest.fail("DA_TEST_POSTGRES_DSN_REQUIRED_IN_CI")
        pytest.skip("PostgreSQL pilot E2E requires DA_TEST_POSTGRES_DSN")
    return value


@pytest.fixture(scope="module", autouse=True)
def migrated_database(postgres_dsn: str) -> Iterator[None]:
    with psycopg.connect(postgres_dsn, autocommit=True) as connection:
        connection.execute((MIGRATIONS / "roles.sql").read_text(encoding="utf-8"))
    PostgresMigrationRunner(PostgresSettings(SecretValue(postgres_dsn)), MIGRATIONS).migrate()
    _clear_pilot_data(postgres_dsn)
    yield
    _clear_pilot_data(postgres_dsn)


def _clear_pilot_data(dsn: str) -> None:
    tables = (
        "research_job_events",
        "research_jobs",
        "research_handoffs",
        "research_evidence_candidates",
        "research_source_snapshots",
        "research_source_candidates",
        "research_attempts",
        "research_audit_events",
        "research_budget_usage",
        "research_runs",
        "research_idempotency",
        "intake_confirmations",
        "intake_facts",
        "intake_audit_events",
        "intake_records",
        "intake_idempotency",
        "reports",
        "audit_events",
        "decisions",
        "idempotency",
        "tenant_runtime_limits",
    )
    with psycopg.connect(dsn, autocommit=True) as connection:
        for table in tables:
            connection.execute(
                psycopg.sql.SQL("DELETE FROM {} WHERE tenant_id = ANY(%s)").format(
                    psycopg.sql.Identifier(table)
                ),
                (list(TENANTS),),
            )


def _authenticator() -> tuple[OidcAuthenticator, Any]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = RSAAlgorithm.to_jwk(private.public_key(), as_dict=True)
    public.update({"kid": "pilot-key", "alg": "RS256", "use": "sig"})
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"keys": [public]}))
    )
    keys = CachedJwksProvider(
        issuer=ISSUER,
        jwks_uri=f"{ISSUER}/jwks.json",
        client=client,
        cache_ttl_seconds=300,
    )
    return (
        OidcAuthenticator(
            OidcPolicy(issuer=ISSUER, audience=AUDIENCE, algorithms=("RS256",)), keys
        ),
        private,
    )


def _token(private: Any, tenant: str, actor: str, role: str, kind: str = "HUMAN") -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": actor,
            "iat": now,
            "nbf": now - 1,
            "exp": now + 600,
            "tenant_id": tenant,
            "role": role,
            "actor_kind": kind,
        },
        private,
        algorithm="RS256",
        headers={"kid": "pilot-key"},
    )


def _headers(
    token: str,
    key: str | None = None,
    *,
    locale: str = "en",
    correlation_id: str | None = None,
) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}", "Accept-Language": locale}
    if key is not None:
        headers["Idempotency-Key"] = key
    if correlation_id is not None:
        headers["X-Correlation-ID"] = correlation_id
    return headers


def _create_intake_and_compile(
    api: TestClient, token_generator: str, token_validator: str, tenant_suffix: str
) -> dict[str, Any]:
    payload = json.loads((FIXTURES / "sales_quote_de.json").read_text(encoding="utf-8"))
    created = api.post(
        "/v1/intakes",
        headers=_headers(token_generator, f"{tenant_suffix}-create", locale="de"),
        json=payload,
    )
    assert created.status_code == 201
    assert created.json()["status"] == "NEEDS_CONFIRMATION"
    fact_id = next(
        item["fact_id"]
        for item in created.json()["verification"]["candidates"]
        if item["fact_type"] == "APPROVAL_CLAIM"
    )
    confirmed = api.post(
        "/v1/intakes/PILOT-QUOTE-001/confirmations",
        headers=_headers(token_validator, f"{tenant_suffix}-confirm", locale="de"),
        json={
            "fact_id": fact_id,
            "action": "CONFIRM",
            "new_value": None,
            "reason": "Freigabebeleg durch einen Menschen geprüft",
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "READY"
    compiled = api.post(
        "/v1/intakes/PILOT-QUOTE-001/compile",
        headers=_headers(token_validator, f"{tenant_suffix}-compile", locale="de"),
    )
    assert compiled.status_code == 201
    assert compiled.json()["decision_outcome"] is None
    return compiled.json()


def test_controlled_sales_quote_pilot_end_to_end(postgres_dsn: str) -> None:
    connections = PostgresConnectionProvider(PostgresSettings(SecretValue(postgres_dsn)))
    decisions = PostgresDecisionRepository(connections)
    intakes = PostgresIntakeRepository(connections)
    research = PostgresResearchRepository(connections)
    jobs = PostgresJobRepository(connections)
    provider = json.loads((FIXTURES / "pilot_provider_response.json").read_text(encoding="utf-8"))
    search = FakeSearchProvider(
        SearchResponse(
            "fake-brave",
            "pilot-v1",
            NOW.isoformat(),
            (SearchResult(provider["url"], provider["title"], "policy", 1, NOW.isoformat()),),
        )
    )
    extractor = FakeContentExtractor(
        {
            provider["url"]: ExtractionResponse(
                content=ExtractedContent(
                    provider["content"],
                    provider["title"],
                    provider["url"],
                    NOW.isoformat(),
                    "text/markdown",
                    200,
                    provider["language"],
                    "fake-firecrawl",
                    "pilot-v1",
                )
            )
        }
    )
    orchestrator = ResearchOrchestrator(
        search,
        extractor,
        research,
        PublicUrlPolicy(Resolver()),
        EvidenceNormalizer(max_content_bytes=100_000),
        EvidencePolicy(primary_domains=("pilot.example",)),
        ResearchEvidenceCompiler(),
        PostgresDecisionEvidenceHandoff(connections),
        policy=ResearchPolicy(provider_budget=10, max_search_results=2, max_extractions=1),
        clock=lambda: NOW,
    )
    submission = ResearchSubmissionService(orchestrator, jobs, jobs)
    authenticator, private = _authenticator()
    log_lines: list[str] = []
    metrics = InMemoryMetrics()
    policy = PolicyContext("PILOT-SALES", "1", "2026-01-01", "10", "25", 24, "50000")
    app = create_app(
        decisions,
        authenticator,
        intakes,
        InMemoryPolicyRegistry({tenant: policy for tenant in TENANTS}),
        research,
        orchestrator,
        research_submission_service=submission,
        logger=JsonEventLogger(log_lines.append),
        metrics=metrics,
        api_version="0.5.0",
    )
    api = TestClient(app)
    tokens = {
        f"{tenant}:{role.lower()}": _token(private, tenant, f"{tenant}-{role.lower()}", role)
        for tenant in TENANTS
        for role in ("GENERATOR", "VALIDATOR", "APPROVER", "AUDITOR")
    }
    tokens["pilot-tenant-a:agent-approver"] = _token(
        private, "pilot-tenant-a", "pilot-agent", "APPROVER", "AGENT"
    )

    approved = _create_intake_and_compile(
        api,
        tokens["pilot-tenant-a:generator"],
        tokens["pilot-tenant-a:validator"],
        "a",
    )
    review = _create_intake_and_compile(
        api,
        tokens["pilot-tenant-b:generator"],
        tokens["pilot-tenant-b:validator"],
        "b",
    )
    assert approved["decision_id"] == review["decision_id"]

    decision_id = review["decision_id"]
    claim_id = review["claims"][0]["id"]
    queued = api.post(
        "/v1/research-runs",
        headers=_headers(
            tokens["pilot-tenant-b:validator"],
            "b-research",
            correlation_id="pilot-correlation-b",
        ),
        json={
            "schema_version": "0.4.0",
            "decision_file_id": decision_id,
            "claim_refs": [claim_id],
            "query": "Which public pricing controls apply?",
            "locale": "de-DE",
            "preferred_languages": ["de", "en"],
            "max_search_results": 1,
            "max_sources_to_extract": 1,
            "allowed_domains": ["pilot.example"],
            "blocked_domains": [],
            "freshness": {"maximum_age_days": 365, "prefer_recent": True},
            "research_policy": "standard",
            "force_refresh": False,
            "refresh_generation": None,
        },
    )
    assert queued.status_code == 202
    assert queued.json()["job_status"] == "QUEUED"
    assert search.calls == [] and extractor.calls == []

    def process(job: Any, cancelled: Any) -> bool:
        run = research.get(TenantContext(job.tenant_id), job.research_run_id)
        assert run is not None and not cancelled()
        result = asyncio.run(
            orchestrator.execute(
                TenantContext(job.tenant_id),
                run.actor_id,
                run.request,
                run.expected_document_hash,
                job.correlation_id,
            )
        )
        return result.status is ResearchStatus.PARTIALLY_COMPLETED

    def worker_time() -> str:
        return "2026-07-30T12:00:01Z"

    worker = ResearchWorker(jobs, process, clock=worker_time)
    assert worker.run_once("pilot-worker", now=worker_time())
    run_id = queued.json()["research_run_id"]
    completed = api.get(
        f"/v1/research-runs/{run_id}",
        headers=_headers(tokens["pilot-tenant-b:validator"]),
    )
    assert completed.json()["status"] == "COMPLETED"
    assert len(search.calls) == len(extractor.calls) == 1

    result_a = api.post(
        f"/v1/decisions/{decision_id}/evaluate",
        headers=_headers(tokens["pilot-tenant-a:validator"], "a-evaluate"),
    )
    result_b = api.post(
        f"/v1/decisions/{decision_id}/evaluate",
        headers=_headers(tokens["pilot-tenant-b:validator"], "b-evaluate"),
    )
    assert result_a.json()["outcome"] == "PASS"
    assert result_b.json()["outcome"] == "REVIEW"
    for tenant, expected in (("pilot-tenant-a", "PASS"), ("pilot-tenant-b", "REVIEW")):
        validator = tokens[f"{tenant}:validator"]
        assert (
            api.post(
                f"/v1/decisions/{decision_id}/transitions",
                headers=_headers(validator, f"{tenant}-validation"),
                json={"target": "VALIDATION"},
            ).status_code
            == 200
        )
        assert (
            api.post(
                f"/v1/decisions/{decision_id}/transitions",
                headers=_headers(validator, f"{tenant}-review"),
                json={"target": "REVIEW"},
            ).status_code
            == 200
        )
        assert expected in {"PASS", "REVIEW"}

    denied_agent = api.post(
        f"/v1/decisions/{decision_id}/transitions",
        headers=_headers(tokens["pilot-tenant-a:agent-approver"], "a-agent-approve"),
        json={"target": "APPROVED"},
    )
    assert denied_agent.status_code == 409
    approved_terminal = api.post(
        f"/v1/decisions/{decision_id}/transitions",
        headers=_headers(tokens["pilot-tenant-a:approver"], "a-human-approve"),
        json={"target": "APPROVED"},
    )
    assert approved_terminal.json()["status"] == "APPROVED"
    review_not_approved = api.post(
        f"/v1/decisions/{decision_id}/transitions",
        headers=_headers(tokens["pilot-tenant-b:approver"], "b-human-approve"),
        json={"target": "APPROVED"},
    )
    assert review_not_approved.status_code == 409

    tenant_a_document = api.get(
        f"/v1/decisions/{decision_id}", headers=_headers(tokens["pilot-tenant-a:auditor"])
    ).json()
    tenant_b_document = api.get(
        f"/v1/decisions/{decision_id}", headers=_headers(tokens["pilot-tenant-b:auditor"])
    ).json()
    assert tenant_a_document["status"] == "APPROVED"
    assert tenant_b_document["status"] == "REVIEW"
    assert not any(item["id"].startswith("research-") for item in tenant_a_document["evidence"])
    assert any(item["id"].startswith("research-") for item in tenant_b_document["evidence"])
    handoff_event = next(
        item
        for item in tenant_b_document["audit_events"]
        if item["event_type"] == "research.evidence-attached"
    )
    assert handoff_event["correlation_id"] == "pilot-correlation-b"
    research_audit = api.get(
        f"/v1/research-runs/{run_id}/audit",
        headers=_headers(tokens["pilot-tenant-b:auditor"]),
    ).json()["items"]
    assert research_audit and {item["correlation_id"] for item in research_audit} == {
        "pilot-correlation-b"
    }

    missing_de = api.get(
        "/v1/decisions/not-present",
        headers=_headers(tokens["pilot-tenant-a:auditor"], locale="de"),
    )
    missing_fallback = api.get(
        "/v1/decisions/not-present",
        headers=_headers(tokens["pilot-tenant-a:auditor"], locale="fr"),
    )
    assert missing_de.json()["message"] != missing_fallback.json()["message"]
    assert metrics.counter("http_requests_total", {"route": "get_decision", "status": "4xx"}) == 2
    parsed_logs = [json.loads(item) for item in log_lines]
    assert all("authorization" not in item for item in parsed_logs)
    assert any(item["correlation_id"] == "pilot-correlation-b" for item in parsed_logs)
