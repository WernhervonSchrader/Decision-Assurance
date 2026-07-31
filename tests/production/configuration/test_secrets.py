import json
from pathlib import Path

import pytest

from decision_assurance.api.runtime import _provider_secret, load_runtime
from decision_assurance.production.contracts import EnvironmentProfile, SecretReference
from decision_assurance.production.secrets import (
    EnvironmentSecretProvider,
    FileSecretProvider,
    SecretResolutionError,
)


def test_environment_provider_is_limited_to_development_and_test() -> None:
    with pytest.raises(ValueError, match="ENVIRONMENT_SECRETS_NOT_ALLOWED"):
        EnvironmentSecretProvider(EnvironmentProfile.PRODUCTION, {"DATABASE_DSN": "canary"})


@pytest.mark.parametrize("value", ["", "changeme", "replace-me", "placeholder", "example-secret"])
def test_missing_or_placeholder_secrets_fail_closed(value: str) -> None:
    provider = EnvironmentSecretProvider(EnvironmentProfile.TEST, {"DATABASE_DSN": value})

    with pytest.raises(SecretResolutionError, match="SECRET_UNAVAILABLE"):
        provider.resolve(SecretReference("DATABASE_DSN"))


def test_secret_value_is_redacted_from_representations_and_errors() -> None:
    canary = "canary-production-secret-7f4c"
    provider = EnvironmentSecretProvider(EnvironmentProfile.TEST, {"DATABASE_DSN": canary})

    secret = provider.resolve(SecretReference("DATABASE_DSN"))

    assert canary not in repr(secret)
    assert canary not in repr(provider)


def test_platform_mounted_secret_files_are_resolved_by_reference(tmp_path: Path) -> None:
    canary = "mounted-canary-secret-9d2a"
    (tmp_path / "database-dsn").write_text(canary, encoding="utf-8")
    provider = FileSecretProvider(tmp_path)

    value = provider.resolve(SecretReference("database-dsn"))

    assert value.value == canary
    assert canary not in repr(provider)
    with pytest.raises(SecretResolutionError):
        provider.resolve(SecretReference("missing-secret"))


def test_provider_secrets_resolve_independently_and_missing_connector_fails_closed(
    tmp_path: Path,
) -> None:
    openai_canary = "mounted-openai-canary-4ce1"  # noqa: S105
    (tmp_path / "OPENAI_API_KEY").write_text(openai_canary, encoding="utf-8")
    provider = FileSecretProvider(tmp_path)

    assert _provider_secret(provider, "OPENAI_API_KEY") == openai_canary
    assert _provider_secret(provider, "FIRECRAWL_API_KEY") is None
    assert openai_canary not in repr(provider)


def test_development_runtime_starts_with_independently_missing_provider_keys(
    tmp_path: Path,
) -> None:
    identities = tmp_path / "identities.json"
    identities.write_text(
        json.dumps(
            {
                "test-token": {
                    "actor_id": "actor-1",
                    "tenant_id": "tenant-a",
                    "role": "GENERATOR",
                    "kind": "HUMAN",
                }
            }
        ),
        encoding="utf-8",
    )
    secret_directory = tmp_path / "secrets"
    secret_directory.mkdir()
    (secret_directory / "OPENAI_API_KEY").write_text("valid-openai-canary", encoding="utf-8")

    app = load_runtime(
        {
            "DA_CONFIG_PATH": "config/deployment/provider-development.example.json",
            "DA_PROFILE": "development",
            "DA_DATABASE_PATH": str(tmp_path / "runtime.db"),
            "DA_IDENTITIES_PATH": str(identities),
            "DA_SECRET_DIRECTORY": str(secret_directory),
        }
    )

    assert app is not None
