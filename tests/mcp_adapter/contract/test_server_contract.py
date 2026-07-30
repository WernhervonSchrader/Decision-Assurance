from __future__ import annotations

from typing import Any, cast

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from decision_assurance.identity import ActorKind, Identity, Role, StaticTokenAuthenticator
from decision_assurance.mcp.auth import DecisionAssuranceTokenVerifier
from decision_assurance.mcp.server import create_mcp_server
from decision_assurance.mcp.service import McpApplicationError, McpResearchService
from decision_assurance.tenancy import TenantContext


class UnusedService:
    pass


class CapturingService:
    def __init__(self) -> None:
        self.identity: Identity | None = None

    def get(self, identity: Identity, request: Any):  # type: ignore[no-untyped-def]
        self.identity = identity
        return McpResearchService.error_response(McpApplicationError("NOT_FOUND"), request.locale)


@pytest.mark.anyio
async def test_server_exposes_exactly_five_bounded_tools() -> None:
    authenticator = StaticTokenAuthenticator(
        {"token": Identity("actor-a", TenantContext("tenant-a"), Role.GENERATOR, ActorKind.HUMAN)}
    )
    server = create_mcp_server(
        cast(McpResearchService, UnusedService()),
        DecisionAssuranceTokenVerifier(authenticator),
        AuthSettings(
            issuer_url=AnyHttpUrl("http://localhost/identity"),
            resource_server_url=AnyHttpUrl("http://localhost:8001"),
            required_scopes=[],
        ),
    )
    tools = await server.list_tools()
    assert {item.name for item in tools} == {
        "research_start",
        "research_get",
        "research_retry",
        "research_cancel",
        "research_handoff",
    }
    serialized = " ".join(str(item.model_dump(mode="json")) for item in tools)
    assert "tenant_id" not in serialized
    assert all(value not in serialized for value in ("crawl_anything", "shell", "filesystem"))


@pytest.mark.anyio
async def test_token_verifier_uses_verified_identity_and_never_returns_bearer_value() -> None:
    verifier = DecisionAssuranceTokenVerifier(
        StaticTokenAuthenticator(
            {
                "real-secret-token": Identity(
                    "actor-a", TenantContext("tenant-a"), Role.VALIDATOR, ActorKind.HUMAN
                )
            }
        )
    )
    access = await verifier.verify_token("real-secret-token")
    assert access is not None
    assert access.token == "[REDACTED]"  # noqa: S105 - redaction sentinel
    assert access.claims is not None and access.claims["tenant_id"] == "tenant-a"
    assert "real-secret-token" not in str(access.model_dump(mode="json"))
    assert await verifier.verify_token("wrong") is None


@pytest.mark.anyio
async def test_streamable_http_authenticates_before_tool_invocation() -> None:
    identity = Identity("actor-a", TenantContext("tenant-a"), Role.GENERATOR, ActorKind.HUMAN)
    authenticator = StaticTokenAuthenticator({"valid-token": identity})
    service = CapturingService()
    server = create_mcp_server(
        cast(McpResearchService, service),
        DecisionAssuranceTokenVerifier(authenticator),
        AuthSettings(
            issuer_url=AnyHttpUrl("http://localhost/identity"),
            resource_server_url=AnyHttpUrl("http://testserver"),
            required_scopes=[],
        ),
        allowed_hosts=("testserver",),
    )
    app = server.streamable_http_app()
    transport = httpx.ASGITransport(app=app)
    async with server.session_manager.run():
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as raw:
            unauthenticated = await raw.post(
                "/mcp",
                headers={"Accept": "application/json, text/event-stream"},
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"},
                    },
                },
            )
            assert unauthenticated.status_code == 401

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Authorization": "Bearer valid-token"},
        ) as authorized:
            async with streamable_http_client("http://testserver/mcp", http_client=authorized) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "research_get",
                        {"request": {"research_run_id": "missing", "locale": "en"}},
                    )
                    assert result.structuredContent is not None
                    assert result.structuredContent["ok"] is False
    assert service.identity == identity
