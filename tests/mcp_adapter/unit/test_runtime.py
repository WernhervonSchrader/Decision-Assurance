import json

import pytest

from decision_assurance.mcp.runtime import load_mcp_runtime


def test_reference_runtime_is_loopback_bounded_and_loads_existing_identity(tmp_path) -> None:  # type: ignore[no-untyped-def]
    identities = tmp_path / "identities.json"
    identities.write_text(
        json.dumps(
            {
                "token": {
                    "actor_id": "actor-a",
                    "tenant_id": "tenant-a",
                    "role": "GENERATOR",
                    "kind": "HUMAN",
                }
            }
        ),
        encoding="utf-8",
    )
    server = load_mcp_runtime(
        {
            "DA_DATABASE_PATH": str(tmp_path / "decision-assurance.db"),
            "DA_IDENTITIES_PATH": str(identities),
        }
    )
    assert server.settings.host == "127.0.0.1"
    assert server.settings.port == 8001
    assert server.settings.streamable_http_path == "/mcp"
    assert server.settings.stateless_http is True
    assert server.settings.max_request_body_size == 1_048_576


def test_configured_runtime_requires_explicit_mcp_resource_security() -> None:
    with pytest.raises(RuntimeError, match="MCP_PRODUCTION_SECURITY_CONFIGURATION_REQUIRED"):
        load_mcp_runtime({"DA_CONFIG_PATH": "config/production.example.json"})
