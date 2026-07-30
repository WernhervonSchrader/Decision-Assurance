from __future__ import annotations

import os
from collections.abc import Mapping
from typing import cast

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl

from ..api.runtime import load_runtime
from ..identity import Authenticator
from ..jobs.repository import JobRepository
from ..repositories.protocols import DecisionRepository
from ..web_research.orchestrator import ResearchOrchestrator
from ..web_research.ports import ResearchRepositoryPort
from ..web_research.service import ResearchSubmissionService
from .auth import DecisionAssuranceTokenVerifier
from .server import create_mcp_server
from .service import McpResearchService


def load_mcp_runtime(environment: dict[str, str] | None = None) -> FastMCP[None]:
    values = dict(environment) if environment is not None else dict(os.environ)
    host = values.get("DA_MCP_HOST", "127.0.0.1")
    port = _integer(values, "DA_MCP_PORT", 8001)
    production_configured = bool(values.get("DA_CONFIG_PATH"))
    issuer = values.get("DA_MCP_ISSUER_URL")
    resource = values.get("DA_MCP_RESOURCE_SERVER_URL")
    allowed_hosts = _csv(values.get("DA_MCP_ALLOWED_HOSTS"))
    allowed_origins = _csv(values.get("DA_MCP_ALLOWED_ORIGINS"))
    if production_configured and (not issuer or not resource or not allowed_hosts):
        raise RuntimeError("MCP_PRODUCTION_SECURITY_CONFIGURATION_REQUIRED")
    issuer = issuer or "http://localhost/identity"
    resource = resource or f"http://{host}:{port}"
    allowed_hosts = allowed_hosts or ("127.0.0.1:*", "localhost:*")
    api = load_runtime(values)
    service = McpResearchService(
        cast(DecisionRepository, api.state.repository),
        cast(ResearchRepositoryPort, api.state.research_repository),
        cast(ResearchOrchestrator, api.state.research_orchestrator),
        submission=cast(
            ResearchSubmissionService | None,
            getattr(api.state, "research_submission_service", None),
        ),
        jobs=cast(JobRepository | None, getattr(api.state, "job_repository", None)),
    )
    authenticator = cast(Authenticator, api.state.authenticator)
    return create_mcp_server(
        service,
        DecisionAssuranceTokenVerifier(authenticator),
        AuthSettings(
            issuer_url=AnyHttpUrl(issuer),
            resource_server_url=AnyHttpUrl(resource),
            required_scopes=[],
        ),
        host=host,
        port=port,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


def _csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    result = tuple(item.strip() for item in value.split(",") if item.strip())
    if len(result) > 50:
        raise RuntimeError("MCP_CONFIGURATION_LIMIT_EXCEEDED")
    return result


def _integer(values: Mapping[str, str], name: str, default: int) -> int:
    try:
        value = int(values.get(name, str(default)))
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer") from error
    if not 1 <= value <= 65_535:
        raise RuntimeError(f"{name} must be a valid port")
    return value


def main() -> None:
    load_mcp_runtime().run(transport="streamable-http")
