import json
from pathlib import Path

import pytest

from decision_assurance.production.config import RuntimeConfig, load_config
from decision_assurance.production.contracts import (
    AuthenticationMode,
    DatabaseBackend,
    EnvironmentProfile,
)


def _production() -> dict[str, object]:
    return {
        "profile": "production",
        "database_backend": "postgresql",
        "authentication_mode": "oidc",
        "secret_provider": "external",
        "database_dsn_secret": "database-dsn",
        "worker_database_dsn_secret": "worker-database-dsn",
        "oidc": {
            "issuer": "https://identity.example",
            "audience": "decision-assurance",
            "jwks_uri": "https://identity.example/jwks.json",
            "algorithms": ["RS256"],
        },
        "egress_allowed_hosts": ["api.search.brave.com", "api.firecrawl.dev"],
        "worker": {"max_attempts": 5, "lease_seconds": 60},
    }


def test_valid_production_profile_is_typed_and_contains_only_secret_reference() -> None:
    config = RuntimeConfig.from_mapping(_production())

    assert config.profile is EnvironmentProfile.PRODUCTION
    assert config.database_backend is DatabaseBackend.POSTGRESQL
    assert config.authentication_mode is AuthenticationMode.OIDC
    assert config.database_dsn_secret.name == "database-dsn"


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (("database_backend",), "sqlite", "PRODUCTION_REQUIRES_POSTGRESQL"),
        (("authentication_mode",), "static", "PRODUCTION_REQUIRES_OIDC"),
        (("secret_provider",), "environment", "EXTERNAL_SECRET_PROVIDER_REQUIRED"),
        (("database_dsn_secret",), "", "INVALID_SECRET_REFERENCE"),
        (("oidc", "issuer"), "http://identity.example", "INVALID_OIDC"),
        (("egress_allowed_hosts",), [], "EGRESS_ALLOWLIST_REQUIRED"),
    ],
)
def test_production_rejects_unsafe_fallbacks(
    path: tuple[str, ...], value: object, reason: str
) -> None:
    raw = _production()
    target = raw
    for part in path[:-1]:
        target = target[part]  # type: ignore[assignment,index]
    target[path[-1]] = value

    with pytest.raises(ValueError, match=reason):
        RuntimeConfig.from_mapping(raw)


def test_environment_has_explicit_precedence_for_non_secret_profile_selection(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(_production()), encoding="utf-8")

    config = load_config(path, {"DA_PROFILE": "staging"})

    assert config.profile is EnvironmentProfile.STAGING
