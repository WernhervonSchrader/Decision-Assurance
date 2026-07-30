from pathlib import Path

import pytest

from decision_assurance.persistence.factory import create_persistence
from decision_assurance.production.contracts import (
    DatabaseBackend,
    EnvironmentProfile,
    SecretValue,
)
from decision_assurance.repositories.sqlite import SqliteDecisionRepository


def test_sqlite_is_available_only_for_non_production_reference_profiles(tmp_path: Path) -> None:
    bundle = create_persistence(
        profile=EnvironmentProfile.TEST,
        backend=DatabaseBackend.SQLITE,
        sqlite_path=tmp_path / "reference.db",
    )

    assert isinstance(bundle.decisions, SqliteDecisionRepository)


def test_production_rejects_sqlite_even_when_a_path_is_supplied(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="PRODUCTION_REQUIRES_POSTGRESQL"):
        create_persistence(
            profile=EnvironmentProfile.PRODUCTION,
            backend=DatabaseBackend.SQLITE,
            sqlite_path=tmp_path / "unsafe.db",
        )


def test_postgresql_requires_a_secret_dsn_reference() -> None:
    with pytest.raises(ValueError, match="POSTGRES_DSN_REQUIRED"):
        create_persistence(
            profile=EnvironmentProfile.PRODUCTION,
            backend=DatabaseBackend.POSTGRESQL,
        )


def test_postgresql_bundle_is_constructed_without_opening_a_connection() -> None:
    bundle = create_persistence(
        profile=EnvironmentProfile.PRODUCTION,
        backend=DatabaseBackend.POSTGRESQL,
        postgres_dsn=SecretValue("postgresql://unreachable.invalid/db"),
    )

    assert bundle.backend is DatabaseBackend.POSTGRESQL
    assert bundle.connections is not None
