from __future__ import annotations

from pathlib import Path

import yaml


def test_keycloak_compose_is_pinned_isolated_and_health_checked() -> None:
    compose = yaml.safe_load(Path("compose.keycloak.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert set(services) == {"keycloak", "keycloak-postgres"}
    postgres = services["keycloak-postgres"]
    assert postgres["environment"]["POSTGRES_DB"] == "keycloak"
    assert postgres["environment"]["POSTGRES_USER"] == "keycloak"
    assert "keycloak-postgres-data" in postgres["volumes"][0]
    assert "healthcheck" in postgres
    assert "POSTGRES_PASSWORD" not in postgres["environment"]
    assert postgres["environment"]["POSTGRES_PASSWORD_FILE"].startswith("/run/secrets/")

    keycloak = services["keycloak"]
    assert keycloak["build"]["dockerfile"] == "Dockerfile.keycloak"
    assert keycloak["user"] == "1000:0"
    assert "healthcheck" in keycloak
    assert keycloak["depends_on"]["keycloak-postgres"]["condition"] == "service_healthy"
    assert all(str(port).startswith("127.0.0.1:") for port in keycloak["ports"])
    assert set(keycloak["secrets"]) == {
        "keycloak-admin-username",
        "keycloak-admin-password",
        "keycloak-db-password",
    }


def test_keycloak_image_is_optimized_non_root_and_never_uses_start_dev() -> None:
    dockerfile = Path("Dockerfile.keycloak").read_text(encoding="utf-8")
    entrypoint = Path("integrations/keycloak/entrypoint.sh").read_text(encoding="utf-8")
    assert "quay.io/keycloak/keycloak:26.7.0" in dockerfile
    assert "kc.sh build" in dockerfile
    assert "USER 1000" in dockerfile
    assert "start-dev" not in dockerfile
    assert "start-dev" not in entrypoint
    assert "exec /opt/keycloak/bin/kc.sh" in entrypoint


def test_only_example_keycloak_secrets_are_tracked() -> None:
    expected = {
        "keycloak-admin-username.example",
        "keycloak-admin-password.example",
        "keycloak-db-password.example",
    }
    assert expected.issubset({path.name for path in Path(".secrets").glob("keycloak-*.example")})
    gitleaks = Path(".gitleaks.toml").read_text(encoding="utf-8")
    for name in expected:
        assert name.removesuffix(".example") in gitleaks
