from __future__ import annotations

import os
from pathlib import Path

from ..production.contracts import SecretReference
from ..production.secrets import FileSecretProvider
from .postgresql import PostgresMigrationRunner, PostgresSettings


def main() -> None:
    directory = os.getenv("DA_SECRET_DIRECTORY")
    reference = os.getenv("DA_DATABASE_DSN_SECRET_REF")
    if not directory or not reference:
        raise RuntimeError("MIGRATION_SECRET_CONFIGURATION_REQUIRED")
    provider = FileSecretProvider(Path(directory))
    dsn = provider.resolve(SecretReference(reference))
    runner = PostgresMigrationRunner(PostgresSettings(dsn))
    runner.migrate()
    if runner.current_version() != "002":
        raise RuntimeError("DATABASE_SCHEMA_VERSION_MISMATCH")
