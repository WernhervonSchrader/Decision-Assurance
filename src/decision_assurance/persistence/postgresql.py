from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from ..production.contracts import SecretValue
from ..tenancy import TenantContext

_MIGRATION_NAME = re.compile(r"^(?P<version>[0-9]{3})_[a-z0-9_]+\.sql$")
_MIGRATION_LOCK = 5_045_304_005


class MigrationIntegrityError(RuntimeError):
    """Raised when a migration sequence or applied checksum is invalid."""


class PersistenceUnavailable(RuntimeError):
    """Stable public error that does not disclose connection credentials."""


class UnsafeDatabaseRole(RuntimeError):
    """Raised when the runtime connection can own schema or bypass RLS."""


@dataclass(frozen=True, slots=True)
class PostgresSettings:
    dsn: SecretValue
    connect_timeout_seconds: int = 5
    application_role: str = "decision_assurance_application"
    migration_role: str = "decision_assurance_migration"

    def __post_init__(self) -> None:
        if not 1 <= self.connect_timeout_seconds <= 60:
            raise ValueError("INVALID_POSTGRES_CONNECT_TIMEOUT")


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    name: str
    path: Path
    checksum: str


def migration_checksum(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def discover_migrations(directory: Path) -> tuple[Migration, ...]:
    migrations: list[Migration] = []
    for path in sorted(directory.glob("[0-9][0-9][0-9]_*.sql")):
        match = _MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            raise MigrationIntegrityError("INVALID_MIGRATION_NAME")
        migrations.append(
            Migration(
                version=match.group("version"),
                name=path.name,
                path=path,
                checksum=migration_checksum(path),
            )
        )
    expected = [f"{number:03d}" for number in range(1, len(migrations) + 1)]
    if [item.version for item in migrations] != expected:
        raise MigrationIntegrityError("MIGRATION_SEQUENCE_GAP")
    if not migrations:
        raise MigrationIntegrityError("NO_MIGRATIONS_FOUND")
    return tuple(migrations)


def packaged_migration_directory() -> Path:
    resource = files("decision_assurance.migrations").joinpath("postgresql")
    return Path(str(resource))


class PostgresConnectionProvider:
    def __init__(self, settings: PostgresSettings):
        self._settings = settings

    def _connect(self, *, autocommit: bool = False) -> Connection[dict[str, Any]]:
        try:
            return psycopg.connect(
                self._settings.dsn.value,
                autocommit=autocommit,
                connect_timeout=self._settings.connect_timeout_seconds,
                row_factory=dict_row,
            )
        except psycopg.Error:
            raise PersistenceUnavailable("POSTGRES_CONNECTION_FAILED") from None

    @contextmanager
    def tenant_connection(self, tenant: TenantContext) -> Iterator[Connection[dict[str, Any]]]:
        with self._connect() as connection, connection.transaction():
            connection.execute(
                "SELECT set_config('decision_assurance.tenant_id', %s, true)",
                (tenant.tenant_id,),
            )
            yield connection

    @contextmanager
    def worker_connection(self) -> Iterator[Connection[dict[str, Any]]]:
        """Unscoped queue session; the worker role has access only to job-owned tables."""
        with self._connect() as connection, connection.transaction():
            yield connection

    def ready(self) -> bool:
        try:
            with self._connect() as connection:
                row = connection.execute("SELECT 1 AS ready").fetchone()
                return row is not None and row["ready"] == 1
        except PersistenceUnavailable:
            return False

    def verify_tenant_scope(self, tenant: TenantContext) -> bool:
        try:
            with self.tenant_connection(tenant) as connection:
                row = connection.execute(
                    "SELECT current_setting('decision_assurance.tenant_id', true) AS tenant_id"
                ).fetchone()
                return row is not None and row["tenant_id"] == tenant.tenant_id
        except PersistenceUnavailable:
            return False

    def assert_safe_application_role(self) -> None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT current_user AS role_name,
                       rolsuper,
                       rolbypassrls,
                       pg_has_role(current_user, %s, 'MEMBER') AS migration_member
                FROM pg_roles
                WHERE rolname = current_user
                """,
                (self._settings.migration_role,),
            ).fetchone()
        if row is None or row["rolsuper"] or row["rolbypassrls"] or row["migration_member"]:
            raise UnsafeDatabaseRole("UNSAFE_APPLICATION_DATABASE_ROLE")


class PostgresMigrationRunner:
    def __init__(
        self,
        settings: PostgresSettings,
        migration_directory: Path | None = None,
    ):
        self._settings = settings
        self._migration_directory = migration_directory or packaged_migration_directory()

    def _connect(self) -> Connection[dict[str, Any]]:
        try:
            return psycopg.connect(
                self._settings.dsn.value,
                autocommit=True,
                connect_timeout=self._settings.connect_timeout_seconds,
                row_factory=dict_row,
            )
        except psycopg.Error:
            raise PersistenceUnavailable("POSTGRES_MIGRATION_CONNECTION_FAILED") from None

    def current_version(self) -> str:
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT to_regclass('public.schema_migrations') AS relation"
            ).fetchone()
            if exists is None or exists["relation"] is None:
                return "000"
            row = connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
            ).fetchone()
            return "000" if row is None else str(row["version"])

    def migrate(self, target_version: str | None = None) -> None:
        migrations = discover_migrations(self._migration_directory)
        known_versions = {item.version for item in migrations}
        if target_version is not None and target_version not in known_versions:
            raise MigrationIntegrityError("UNKNOWN_MIGRATION_TARGET")

        with self._connect() as connection:
            connection.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_LOCK,))
            try:
                with connection.transaction():
                    connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS schema_migrations (
                            version TEXT PRIMARY KEY,
                            migration_name TEXT NOT NULL UNIQUE,
                            checksum TEXT NOT NULL,
                            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                applied = {
                    str(row["version"]): str(row["checksum"])
                    for row in connection.execute(
                        "SELECT version, checksum FROM schema_migrations"
                    ).fetchall()
                }
                for migration in migrations:
                    if target_version is not None and migration.version > target_version:
                        break
                    existing = applied.get(migration.version)
                    if existing is not None:
                        if existing != migration.checksum:
                            raise MigrationIntegrityError("APPLIED_MIGRATION_CHECKSUM_MISMATCH")
                        continue
                    with connection.transaction():
                        connection.execute(migration.path.read_text(encoding="utf-8"))
                        connection.execute(
                            """
                            INSERT INTO schema_migrations
                                (version, migration_name, checksum)
                            VALUES (%s, %s, %s)
                            """,
                            (migration.version, migration.name, migration.checksum),
                        )
            finally:
                connection.execute("SELECT pg_advisory_unlock(%s)", (_MIGRATION_LOCK,))
