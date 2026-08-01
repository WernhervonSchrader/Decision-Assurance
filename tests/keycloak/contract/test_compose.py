from __future__ import annotations

from pathlib import Path

import yaml


def test_keycloak_compose_is_pinned_isolated_and_health_checked() -> None:
    compose = yaml.safe_load(Path("compose.keycloak.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert set(services) == {"keycloak", "keycloak-bootstrap", "keycloak-postgres"}
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
    assert set(keycloak["secrets"]) == {"keycloak-db-password"}

    bootstrap = services["keycloak-bootstrap"]
    assert bootstrap["profiles"] == ["bootstrap"]
    assert bootstrap["user"] == "1000:0"
    assert bootstrap["restart"] == "no"
    assert bootstrap["logging"]["driver"] == "none"
    assert bootstrap["entrypoint"] == [
        "/opt/keycloak/bin/decision-assurance-bootstrap-entrypoint.sh"
    ]
    assert bootstrap["command"] == [
        "bootstrap-admin",
        "user",
        "--optimized",
        "--username:env",
        "DA_KEYCLOAK_BOOTSTRAP_USERNAME",
        "--password:env",
        "DA_KEYCLOAK_BOOTSTRAP_PASSWORD",
        "--no-prompt",
    ]
    assert set(bootstrap["secrets"]) == {
        "keycloak-admin-username",
        "keycloak-admin-password",
        "keycloak-db-password",
    }
    assert "ports" not in bootstrap
    assert bootstrap["depends_on"]["keycloak-postgres"]["condition"] == "service_healthy"


def test_keycloak_image_is_optimized_non_root_and_never_uses_start_dev() -> None:
    dockerfile = Path("Dockerfile.keycloak").read_text(encoding="utf-8")
    entrypoint = Path("integrations/keycloak/entrypoint.sh").read_text(encoding="utf-8")
    bootstrap_entrypoint = Path("integrations/keycloak/bootstrap-entrypoint.sh").read_text(
        encoding="utf-8"
    )
    assert "quay.io/keycloak/keycloak:26.7.0" in dockerfile
    assert "kc.sh build" in dockerfile
    assert "USER 1000" in dockerfile
    assert "start-dev" not in dockerfile
    assert "start-dev" not in entrypoint
    assert "start-dev" not in bootstrap_entrypoint
    assert "exec /opt/keycloak/bin/kc.sh" in entrypoint
    assert "KC_BOOTSTRAP_ADMIN_" not in entrypoint
    assert "KC_BOOTSTRAP_ADMIN_" not in bootstrap_entrypoint
    assert "DA_KEYCLOAK_BOOTSTRAP_USERNAME" in bootstrap_entrypoint
    assert "DA_KEYCLOAK_BOOTSTRAP_PASSWORD" in bootstrap_entrypoint
    assert "\\[org\\.keycloak\\.services\\]" in bootstrap_entrypoint
    assert "KC-SERVICES0077:[[:space:]]" in bootstrap_entrypoint
    assert "[REDACTED_BOOTSTRAP_ADMIN]" in bootstrap_entrypoint
    assert "decision-assurance-bootstrap-entrypoint.sh" in dockerfile


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


def test_ci_secrets_are_read_only_for_the_non_root_keycloak_process() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert (
        "chmod 0444 .secrets/keycloak-admin-username "
        ".secrets/keycloak-admin-password .secrets/keycloak-db-password"
    ) in workflow
    assert "logs --no-color keycloak" in workflow
    assert "keycloak-bootstrap" in workflow
    assert "assert_no_secret_values.py" in workflow
    assert "bootstrap-output" in workflow
    assert "cat " not in workflow
