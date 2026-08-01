from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[3]


def test_controlled_pilot_compose_has_one_public_edge_and_private_core() -> None:
    compose = yaml.safe_load((ROOT / "compose.controlled-pilot.yaml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert set(services) == {
        "postgres",
        "migrate",
        "api",
        "worker",
        "mcp",
        "keycloak-postgres",
        "keycloak",
        "keycloak-bootstrap",
        "pilot-ui",
        "edge",
    }
    assert services["edge"]["ports"] == ["80:8080", "443:8443"]
    assert all("ports" not in value for name, value in services.items() if name != "edge")
    assert services["pilot-ui"]["read_only"] is True
    assert services["edge"]["read_only"] is True
    assert services["keycloak-bootstrap"]["profiles"] == ["bootstrap"]
    assert services["keycloak-bootstrap"]["logging"]["driver"] == "none"


def test_compose_uses_secret_files_and_contains_no_inline_credentials() -> None:
    compose_text = (ROOT / "compose.controlled-pilot.yaml").read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_text)

    assert all(value["file"].startswith("./.secrets/") for value in compose["secrets"].values())
    assert "POSTGRES_PASSWORD:" not in compose_text
    assert "KC_BOOTSTRAP_ADMIN_PASSWORD" not in compose_text
    assert "localhost" not in compose_text and "127.0.0.1" not in compose_text


def test_caddy_contract_is_https_only_host_bounded_and_strips_forwarded_headers() -> None:
    caddy = (ROOT / "deploy" / "edge" / "Caddyfile").read_text(encoding="utf-8")

    assert "http://{$DA_PUBLIC_HOST}:8080" in caddy
    assert "redir https://{$DA_PUBLIC_HOST}{uri} permanent" in caddy
    assert "https://{$DA_PUBLIC_HOST}:8443" in caddy
    assert "https://{$DA_IDENTITY_HOST}:8443" in caddy
    assert "max_size 1MB" in caddy
    assert "header_up -Forwarded" in caddy
    assert "header_up -X-Forwarded-*" in caddy
    for header in (
        "Strict-Transport-Security",
        "Content-Security-Policy",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
    ):
        assert header in caddy
    assert "respond 404" in caddy


def test_new_images_declare_non_root_runtime_users() -> None:
    ui = (ROOT / "Dockerfile.pilot-ui").read_text(encoding="utf-8")
    edge = (ROOT / "Dockerfile.edge").read_text(encoding="utf-8")

    assert "USER 10001:10001" in ui
    assert "USER 1000:1000" in edge
    assert "node:24.15.0-bookworm-slim" in ui
