from pathlib import Path

import pytest

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
