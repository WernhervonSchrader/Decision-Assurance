from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import httpx
import uvicorn
from fastapi import FastAPI

from ..identity import ActorKind, Identity, Role, StaticTokenAuthenticator
from ..intake.codec import policy_from_dict
from ..intake.repository import SqliteIntakeRepository
from ..intake.verification import InMemoryPolicyRegistry
from ..jobs.postgresql import PostgresJobRepository
from ..oidc.factory import create_authenticator
from ..persistence.factory import create_persistence
from ..production.config import RuntimeConfig, load_config
from ..production.contracts import AuthenticationMode, SecretReference
from ..production.egress import HttpsEgressAllowlist
from ..production.ports import SecretProviderPort
from ..production.secrets import EnvironmentSecretProvider
from ..repositories.sqlite import SqliteDecisionRepository
from ..tenancy import TenantContext
from ..web_research.compiler import (
    PostgresDecisionEvidenceHandoff,
    ResearchEvidenceCompiler,
    SqliteDecisionEvidenceHandoff,
)
from ..web_research.evidence_policy import EvidencePolicy
from ..web_research.normalization import EvidenceNormalizer
from ..web_research.orchestrator import ResearchOrchestrator, ResearchPolicy
from ..web_research.providers.brave import BraveSearchProvider
from ..web_research.providers.firecrawl import FirecrawlContentExtractor
from ..web_research.repository import SqliteResearchRepository
from ..web_research.service import ResearchSubmissionService
from ..web_research.url_policy import PublicUrlPolicy, SystemResolver
from .app import create_app


def load_runtime(
    environment: dict[str, str] | None = None,
    *,
    external_secrets: SecretProviderPort | None = None,
    oidc_http_client: httpx.Client | None = None,
) -> FastAPI:
    values = environment if environment is not None else os.environ
    if config_path := values.get("DA_CONFIG_PATH"):
        config = load_config(Path(config_path), values)
        return _load_configured_runtime(
            config,
            values,
            external_secrets=external_secrets,
            oidc_http_client=oidc_http_client,
        )
    return _load_reference_runtime(values)


def _load_reference_runtime(values: Mapping[str, str]) -> FastAPI:
    database_value = values.get("DA_DATABASE_PATH")
    identities_value = values.get("DA_IDENTITIES_PATH")
    if not database_value or not identities_value:
        raise RuntimeError("DA_DATABASE_PATH and DA_IDENTITIES_PATH are required")
    identities_path = Path(identities_value)
    raw = cast(dict[str, dict[str, Any]], json.loads(identities_path.read_text(encoding="utf-8")))
    identities = {
        token: Identity(
            actor_id=str(item["actor_id"]),
            tenant=TenantContext(str(item["tenant_id"])),
            role=Role(str(item["role"])),
            kind=ActorKind(str(item["kind"])),
        )
        for token, item in raw.items()
    }
    repository = SqliteDecisionRepository(Path(database_value))
    intake_repository = SqliteIntakeRepository(Path(database_value))
    research_repository = SqliteResearchRepository(Path(database_value))
    repository.initialize()
    intake_repository.initialize()
    research_repository.initialize()
    policies: dict[str, Any] = {}
    if policies_value := values.get("DA_POLICIES_PATH"):
        policies = json.loads(Path(policies_value).read_text(encoding="utf-8"))
    url_policy = PublicUrlPolicy(SystemResolver())
    max_content_bytes = _integer(values, "WEB_RESEARCH_MAX_CONTENT_BYTES", 1_000_000)
    research_policy = ResearchPolicy(
        provider_budget=_integer(values, "WEB_RESEARCH_PROVIDER_BUDGET", 100),
        cache_ttl_seconds=_integer(values, "WEB_RESEARCH_CACHE_TTL_SECONDS", 86_400),
        max_content_bytes=max_content_bytes,
        max_search_results=_integer(values, "WEB_RESEARCH_MAX_RESULTS", 10),
        max_extractions=_integer(values, "WEB_RESEARCH_MAX_EXTRACTIONS", 5),
    )
    research_orchestrator = ResearchOrchestrator(
        BraveSearchProvider(
            api_key=values.get("BRAVE_SEARCH_API_KEY"),
            base_url=values.get("BRAVE_SEARCH_BASE_URL", "https://api.search.brave.com"),
            timeout_seconds=_number(values, "BRAVE_SEARCH_TIMEOUT_SECONDS", 10.0),
        ),
        FirecrawlContentExtractor(
            api_key=values.get("FIRECRAWL_API_KEY"),
            url_policy=url_policy,
            base_url=values.get("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev"),
            timeout_seconds=_number(values, "FIRECRAWL_TIMEOUT_SECONDS", 20.0),
            max_content_bytes=max_content_bytes,
        ),
        research_repository,
        url_policy,
        EvidenceNormalizer(
            max_content_bytes=max_content_bytes,
            cache_ttl_seconds=research_policy.cache_ttl_seconds,
        ),
        EvidencePolicy(),
        ResearchEvidenceCompiler(),
        SqliteDecisionEvidenceHandoff(Path(database_value)),
        policy=research_policy,
    )
    return create_app(
        repository,
        StaticTokenAuthenticator(identities),
        intake_repository,
        InMemoryPolicyRegistry(
            {tenant_id: policy_from_dict(item) for tenant_id, item in policies.items()}
        ),
        research_repository,
        research_orchestrator,
    )


def _load_configured_runtime(
    config: RuntimeConfig,
    values: Mapping[str, str],
    *,
    external_secrets: SecretProviderPort | None,
    oidc_http_client: httpx.Client | None,
) -> FastAPI:
    if config.secret_provider.value == "external":
        if external_secrets is None:
            raise RuntimeError("EXTERNAL_SECRET_PROVIDER_REQUIRED")
        secrets = external_secrets
    else:
        secrets = EnvironmentSecretProvider(config.profile, values)
    database_dsn = secrets.resolve(config.database_dsn_secret)
    persistence = create_persistence(
        profile=config.profile,
        backend=config.database_backend,
        postgres_dsn=database_dsn,
    )
    if persistence.connections is None or config.oidc is None:
        raise RuntimeError("CONFIGURED_PRODUCTION_ADAPTERS_REQUIRED")
    oidc_client = oidc_http_client or httpx.Client(follow_redirects=False, timeout=5.0)
    authenticator = create_authenticator(
        profile=config.profile,
        mode=AuthenticationMode.OIDC,
        oidc_policy=config.oidc.policy,
        jwks_uri=config.oidc.jwks_uri,
        http_client=oidc_client,
    )
    egress = HttpsEgressAllowlist(config.egress_allowed_hosts)
    runtime_tenant = TenantContext("runtime-validation")
    brave_base = egress.validate(
        runtime_tenant,
        values.get("BRAVE_SEARCH_BASE_URL", "https://api.search.brave.com"),
    ).rstrip("/")
    firecrawl_base = egress.validate(
        runtime_tenant,
        values.get("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev"),
    ).rstrip("/")
    brave_key = secrets.resolve(
        SecretReference(
            values.get("DA_BRAVE_API_KEY_SECRET_REF", "decision-assurance-brave-api-key")
        )
    )
    firecrawl_key = secrets.resolve(
        SecretReference(
            values.get("DA_FIRECRAWL_API_KEY_SECRET_REF", "decision-assurance-firecrawl-api-key")
        )
    )
    url_policy = PublicUrlPolicy(SystemResolver())
    max_content_bytes = _integer(values, "WEB_RESEARCH_MAX_CONTENT_BYTES", 1_000_000)
    policy = ResearchPolicy(
        provider_budget=_integer(values, "WEB_RESEARCH_PROVIDER_BUDGET", 100),
        cache_ttl_seconds=_integer(values, "WEB_RESEARCH_CACHE_TTL_SECONDS", 86_400),
        max_content_bytes=max_content_bytes,
        max_search_results=_integer(values, "WEB_RESEARCH_MAX_RESULTS", 10),
        max_extractions=_integer(values, "WEB_RESEARCH_MAX_EXTRACTIONS", 5),
    )
    orchestrator = ResearchOrchestrator(
        BraveSearchProvider(api_key=brave_key.value, base_url=brave_base),
        FirecrawlContentExtractor(
            api_key=firecrawl_key.value,
            url_policy=url_policy,
            base_url=firecrawl_base,
            max_content_bytes=max_content_bytes,
        ),
        persistence.research,
        url_policy,
        EvidenceNormalizer(
            max_content_bytes=max_content_bytes,
            cache_ttl_seconds=policy.cache_ttl_seconds,
        ),
        EvidencePolicy(),
        ResearchEvidenceCompiler(),
        PostgresDecisionEvidenceHandoff(persistence.connections),
        policy=policy,
    )
    jobs = PostgresJobRepository(persistence.connections, config.worker_policy)
    submission = ResearchSubmissionService(orchestrator, jobs, jobs)
    policies: dict[str, Any] = {}
    if policies_value := values.get("DA_POLICIES_PATH"):
        policies = json.loads(Path(policies_value).read_text(encoding="utf-8"))
    app = create_app(
        persistence.decisions,
        authenticator,
        persistence.intake,
        InMemoryPolicyRegistry(
            {tenant_id: policy_from_dict(item) for tenant_id, item in policies.items()}
        ),
        persistence.research,
        orchestrator,
        submission,
    )
    app.state.job_repository = jobs
    return app


def _integer(values: Mapping[str, str], name: str, default: int) -> int:
    try:
        return int(values.get(name, str(default)))
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer") from error


def _number(values: Mapping[str, str], name: str, default: float) -> float:
    try:
        return float(values.get(name, str(default)))
    except ValueError as error:
        raise RuntimeError(f"{name} must be a number") from error


def main() -> None:
    uvicorn.run(load_runtime(), host="127.0.0.1", port=8000, log_level="info")
