from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import uvicorn
from fastapi import FastAPI

from ..identity import ActorKind, Identity, Role, StaticTokenAuthenticator
from ..intake.codec import policy_from_dict
from ..intake.repository import SqliteIntakeRepository
from ..intake.verification import InMemoryPolicyRegistry
from ..repositories.sqlite import SqliteDecisionRepository
from ..tenancy import TenantContext
from ..web_research.compiler import ResearchEvidenceCompiler, SqliteDecisionEvidenceHandoff
from ..web_research.evidence_policy import EvidencePolicy
from ..web_research.normalization import EvidenceNormalizer
from ..web_research.orchestrator import ResearchOrchestrator, ResearchPolicy
from ..web_research.providers.brave import BraveSearchProvider
from ..web_research.providers.firecrawl import FirecrawlContentExtractor
from ..web_research.repository import SqliteResearchRepository
from ..web_research.url_policy import PublicUrlPolicy, SystemResolver
from .app import create_app


def load_runtime(environment: dict[str, str] | None = None) -> FastAPI:
    values = environment if environment is not None else os.environ
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
