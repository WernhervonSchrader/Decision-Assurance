from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from decision_assurance.api.app import create_app
from decision_assurance.identity import Role
from decision_assurance.oidc.authenticator import OidcAuthenticator
from decision_assurance.oidc.jwks import CachedJwksProvider
from decision_assurance.production.contracts import OidcPolicy
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.security_events import InMemorySecurityEventSink
from decision_assurance.tenancy import TenantContext
from decision_assurance.web_research.compiler import (
    ResearchEvidenceCompiler,
    SqliteDecisionEvidenceHandoff,
)
from decision_assurance.web_research.contracts import (
    ExtractedContent,
    ExtractionResponse,
    SearchResponse,
    SearchResult,
)
from decision_assurance.web_research.evidence_policy import EvidencePolicy
from decision_assurance.web_research.normalization import EvidenceNormalizer
from decision_assurance.web_research.orchestrator import ResearchOrchestrator, ResearchPolicy
from decision_assurance.web_research.repository import SqliteResearchRepository
from decision_assurance.web_research.url_policy import PublicUrlPolicy
from tests.keycloak.e2e.support import (
    KEYCLOAK_URL,
    REALM,
    pkce_access_token,
    require_live_keycloak,
    restart_keycloak,
    temporary_user,
)

pytestmark = pytest.mark.keycloak_e2e
NOW = datetime(2026, 7, 31, tzinfo=timezone.utc)
ROOT = Path(__file__).parents[3]


class Resolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        del hostname
        return ("93.184.216.34",)


class Search:
    provider_id = "fake-openai"

    def __init__(self) -> None:
        self.calls = 0

    async def search(self, request):  # type: ignore[no-untyped-def]
        del request
        self.calls += 1
        return SearchResponse(
            "fake-openai",
            "v1",
            NOW.isoformat(),
            (SearchResult("https://example.com/rule", "Rule", "", 1, NOW.isoformat()),),
        )


class Extractor:
    provider_id = "fake-firecrawl"

    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, request):  # type: ignore[no-untyped-def]
        self.calls += 1
        return ExtractionResponse(
            content=ExtractedContent(
                "Authoritative rule " * 50,
                "Rule",
                request.url,
                NOW.isoformat(),
                "text/markdown",
                200,
                "en",
                "fake-firecrawl",
                "v1",
            )
        )


def _authenticator() -> OidcAuthenticator:
    issuer = f"{KEYCLOAK_URL}/realms/{REALM}"
    return OidcAuthenticator(
        OidcPolicy(
            issuer=issuer,
            audience="decision-assurance-api",
            algorithms=("RS256",),
            role_claim="realm_access.roles",
            organization_claim="organization",
            groups_claim="groups",
            authorized_parties=("decision-assurance-e2e",),
            required_scopes=("da.api",),
            allow_insecure_loopback=True,
        ),
        CachedJwksProvider(
            issuer=issuer,
            jwks_uri=f"{issuer}/protocol/openid-connect/certs",
            client=httpx.Client(follow_redirects=False, timeout=5.0),
            allow_insecure_loopback=True,
        ),
    )


def _headers(token: str, key: str | None = None, tenant: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if key:
        headers["Idempotency-Key"] = key
    if tenant:
        headers["X-Tenant-ID"] = tenant
    return headers


def test_pkce_identity_tenant_guard_and_authenticated_research_regression(tmp_path: Path) -> None:
    require_live_keycloak()
    with temporary_user(
        tenant_id="tenant-a", roles=("decision_author", "research_operator")
    ) as user:
        token = pkce_access_token(user)
        identity = _authenticator().authenticate(token)
        assert identity.tenant.tenant_id == "tenant-a"
        assert {Role.GENERATOR, Role.RESEARCH_OPERATOR}.issubset(identity.roles)

        database = tmp_path / "keycloak-research.db"
        decisions = SqliteDecisionRepository(database)
        research = SqliteResearchRepository(database)
        decisions.initialize()
        research.initialize()
        document = json.loads((ROOT / "examples/decision-cases/low-risk-pass.json").read_text())
        decisions.create_decision(TenantContext("tenant-a"), copy.deepcopy(document))
        search = Search()
        extractor = Extractor()
        orchestrator = ResearchOrchestrator(
            search,
            extractor,
            research,
            PublicUrlPolicy(Resolver()),
            EvidenceNormalizer(max_content_bytes=100_000),
            EvidencePolicy(primary_domains=("example.com",)),
            ResearchEvidenceCompiler(),
            SqliteDecisionEvidenceHandoff(database),
            policy=ResearchPolicy(provider_budget=4, max_search_results=1, max_extractions=1),
            clock=lambda: NOW,
        )
        events = InMemorySecurityEventSink()
        client = TestClient(
            create_app(
                decisions,
                _authenticator(),
                research_repository=research,
                research_orchestrator=orchestrator,
                security_events=events,
            )
        )
        mismatch = client.get(
            f"/v1/decisions/{document['decision_id']}",
            headers=_headers(token, tenant="tenant-b"),
        )
        assert mismatch.status_code == 403
        assert search.calls == extractor.calls == 0

        created = client.post(
            "/v1/research-runs",
            headers=_headers(token, "keycloak-research"),
            json={
                "schema_version": "0.4.0",
                "decision_file_id": document["decision_id"],
                "claim_refs": [document["claims"][0]["id"]],
                "query": "site:example.com rule",
                "locale": "en-US",
                "preferred_languages": ["en"],
                "max_search_results": 1,
                "max_sources_to_extract": 1,
                "allowed_domains": ["example.com"],
                "blocked_domains": [],
                "freshness": {"maximum_age_days": 3650, "prefer_recent": True},
                "research_policy": "standard",
                "force_refresh": False,
                "refresh_generation": None,
            },
        )
        assert created.status_code == 201
        assert created.json()["evidence_count"] == 1
        assert search.calls == extractor.calls == 1
        assert events.events[-1].reason_code == "AUTH_ALLOWED"


def test_multiple_keycloak_roles_do_not_bypass_actor_independence(tmp_path: Path) -> None:
    require_live_keycloak()
    with temporary_user(
        tenant_id="tenant-a",
        roles=("decision_author", "decision_reviewer", "decision_approver"),
    ) as user:
        token = pkce_access_token(user)
        repository = SqliteDecisionRepository(tmp_path / "independence.db")
        repository.initialize()
        client = TestClient(create_app(repository, _authenticator()))
        document = json.loads((ROOT / "examples/decision-cases/low-risk-pass.json").read_text())
        document["created_by"] = {"id": user.user_id, "role": "GENERATOR", "kind": "HUMAN"}
        created = client.post("/v1/decisions", headers=_headers(token, "kc-create"), json=document)
        assert created.status_code == 201
        rejected = client.post(
            f"/v1/decisions/{document['decision_id']}/transitions",
            headers=_headers(token, "kc-self-validate"),
            json={"target": "VALIDATION"},
        )
        assert rejected.status_code == 409
        assert "GENERATOR_VALIDATOR_NOT_SEPARATE" in rejected.json()["details"]["reason_codes"]


def test_keycloak_restart_preserves_realm_and_temporary_identity() -> None:
    require_live_keycloak()
    with temporary_user(tenant_id="tenant-persist", roles=("readonly",)) as user:
        before = _authenticator().authenticate(pkce_access_token(user))
        restart_keycloak()
        after = _authenticator().authenticate(pkce_access_token(user))
        assert before.actor_id == after.actor_id == user.user_id
        assert after.tenant.tenant_id == "tenant-persist"
        assert Role.READONLY in after.roles
