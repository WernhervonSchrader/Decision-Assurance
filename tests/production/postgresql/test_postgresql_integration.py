from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg import Connection

from decision_assurance.persistence.postgresql import (
    MigrationIntegrityError,
    PostgresMigrationRunner,
    PostgresSettings,
)
from decision_assurance.production.contracts import SecretValue

ROOT = Path(__file__).parents[3]
MIGRATIONS = ROOT / "migrations" / "postgresql"
pytestmark = pytest.mark.postgresql


@pytest.fixture(scope="module")
def postgres_dsn() -> str:
    value = os.getenv("DA_TEST_POSTGRES_DSN")
    if not value:
        if os.getenv("CI"):
            pytest.fail("DA_TEST_POSTGRES_DSN_REQUIRED_IN_CI")
        pytest.skip("PostgreSQL integration requires DA_TEST_POSTGRES_DSN")
    return value


@pytest.fixture(scope="module", autouse=True)
def migrated_database(postgres_dsn: str) -> Iterator[None]:
    with psycopg.connect(postgres_dsn, autocommit=True) as connection:
        connection.execute((MIGRATIONS / "roles.sql").read_text(encoding="utf-8"))
    runner = PostgresMigrationRunner(PostgresSettings(SecretValue(postgres_dsn)), MIGRATIONS)
    runner.migrate()
    yield


def test_migrations_are_repeatable_and_reach_expected_version(postgres_dsn: str) -> None:
    runner = PostgresMigrationRunner(PostgresSettings(SecretValue(postgres_dsn)), MIGRATIONS)

    runner.migrate()

    assert runner.current_version() == "002"


def test_failed_migration_rolls_back_without_advancing_ledger(
    postgres_dsn: str, tmp_path: Path
) -> None:
    for name in ("001_v0_4_baseline.sql", "002_production_foundation_v0_5.sql"):
        shutil.copyfile(MIGRATIONS / name, tmp_path / name)
    (tmp_path / "003_invalid.sql").write_text(
        "CREATE TABLE migration_rollback_probe (value TEXT);\nNOT VALID SQL;\n",
        encoding="utf-8",
    )
    runner = PostgresMigrationRunner(PostgresSettings(SecretValue(postgres_dsn)), tmp_path)

    with pytest.raises(psycopg.Error):
        runner.migrate()

    with psycopg.connect(postgres_dsn) as connection:
        version = connection.execute("SELECT max(version) FROM schema_migrations").fetchone()
        probe = connection.execute(
            "SELECT to_regclass('public.migration_rollback_probe')"
        ).fetchone()
    assert version == ("002",)
    assert probe == (None,)


def test_applied_migration_checksum_drift_is_rejected(postgres_dsn: str, tmp_path: Path) -> None:
    for name in ("001_v0_4_baseline.sql", "002_production_foundation_v0_5.sql"):
        shutil.copyfile(MIGRATIONS / name, tmp_path / name)
    first = tmp_path / "001_v0_4_baseline.sql"
    first.write_text(first.read_text(encoding="utf-8") + "\n-- drift\n", encoding="utf-8")
    runner = PostgresMigrationRunner(PostgresSettings(SecretValue(postgres_dsn)), tmp_path)

    with pytest.raises(MigrationIntegrityError, match="CHECKSUM_MISMATCH"):
        runner.migrate()


def _as_role(connection: Connection[tuple[object, ...]], role: str, tenant_id: str) -> None:
    connection.execute(f"SET ROLE {role}")  # noqa: S608 - fixed test-only role names
    connection.execute(
        "SELECT set_config('decision_assurance.tenant_id', %s, false)",
        (tenant_id,),
    )


def test_application_role_cannot_read_or_write_across_tenants(postgres_dsn: str) -> None:
    with psycopg.connect(postgres_dsn, autocommit=True) as owner:
        owner.execute("DELETE FROM decisions WHERE tenant_id IN ('rls-tenant-a', 'rls-tenant-b')")
        owner.execute(
            """
            INSERT INTO decisions (tenant_id, decision_id, document_json)
            VALUES ('rls-tenant-a', 'decision-a', '{}'),
                   ('rls-tenant-b', 'decision-b', '{}')
            """
        )

    with psycopg.connect(postgres_dsn, autocommit=True) as application:
        _as_role(application, "decision_assurance_application", "rls-tenant-a")
        visible = application.execute(
            "SELECT tenant_id FROM decisions ORDER BY tenant_id"
        ).fetchall()
        updated = application.execute(
            "UPDATE decisions SET document_json = '{\"changed\": true}' "
            "WHERE tenant_id = 'rls-tenant-b'"
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            application.execute(
                "INSERT INTO decisions (tenant_id, decision_id, document_json) "
                "VALUES ('rls-tenant-b', 'cross-tenant', '{}')"
            )

    assert visible == [("rls-tenant-a",)]
    assert updated.rowcount == 0


def test_no_tenant_context_is_fail_closed(postgres_dsn: str) -> None:
    with psycopg.connect(postgres_dsn, autocommit=True) as application:
        application.execute("SET ROLE decision_assurance_application")
        visible = application.execute("SELECT tenant_id FROM decisions").fetchall()

    assert visible == []


def test_runtime_roles_are_non_owner_and_cannot_bypass_rls(postgres_dsn: str) -> None:
    with psycopg.connect(postgres_dsn) as connection:
        rows = connection.execute(
            """
            SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls
            FROM pg_roles
            WHERE rolname IN (
                'decision_assurance_application',
                'decision_assurance_operations_readonly',
                'decision_assurance_audit_export'
            )
            """
        ).fetchall()
        ledger_privileges = connection.execute(
            "SELECT has_table_privilege('decision_assurance_application', "
            "'schema_migrations', 'INSERT,UPDATE,DELETE')"
        ).fetchone()

    assert len(rows) == 3
    assert all(not any(row[1:]) for row in rows)
    assert ledger_privileges == (False,)
