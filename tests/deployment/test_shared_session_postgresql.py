from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest
from cryptography.fernet import Fernet
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from decision_assurance.deployment.postgresql import PostgresAcceptanceAudit
from decision_assurance.events.registry import EventEnvelope
from decision_assurance.persistence.postgresql import (
    PostgresConnectionProvider,
    PostgresMigrationRunner,
    PostgresSettings,
)
from decision_assurance.pilot_ui.session import SensitiveToken
from decision_assurance.pilot_ui.session_postgresql import PostgresSessionStore
from decision_assurance.production.contracts import SecretValue
from decision_assurance.tenancy import TenantContext

pytestmark = pytest.mark.postgresql
MIGRATIONS = Path(__file__).parents[2] / "migrations" / "postgresql"


def _application_dsn(dsn: str) -> str:
    role = "da_pr8_application_test"
    with psycopg.connect(dsn, autocommit=True) as bootstrap:
        if (
            bootstrap.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
            is None
        ):
            bootstrap.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal("postgres")
                )
            )
        else:
            bootstrap.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal("postgres")
                )
            )
        bootstrap.execute(
            sql.SQL("GRANT decision_assurance_application TO {}").format(sql.Identifier(role))
        )
    values = conninfo_to_dict(dsn)
    values.update({"user": role, "password": "postgres"})
    return make_conninfo(**values)


def test_two_bff_instances_share_and_revoke_encrypted_session() -> None:
    dsn = os.environ["DA_TEST_POSTGRES_DSN"]
    with psycopg.connect(dsn, autocommit=True) as bootstrap:
        bootstrap.execute((MIGRATIONS / "roles.sql").read_text(encoding="utf-8"))
    settings = PostgresSettings(SecretValue(dsn))
    PostgresMigrationRunner(settings, MIGRATIONS).migrate()
    connections = PostgresConnectionProvider(PostgresSettings(SecretValue(_application_dsn(dsn))))

    def clock() -> datetime:
        return datetime.now(timezone.utc)

    kwargs = {
        "session_pepper": b"p" * 32,
        "envelope_key": Fernet.generate_key(),
        "clock": clock,
    }
    first = PostgresSessionStore(connections, **kwargs)
    second = PostgresSessionStore(connections, **kwargs)
    assert first.ready()
    with psycopg.connect(dsn) as inspection:
        rls = inspection.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE oid = 'decision_assurance_private.browser_sessions'::regclass"
        ).fetchone()
    assert rls == (True, True)
    identity = {
        "actor_id": "approver-a",
        "tenant_id": "tenant-a",
        "actor_kind": "HUMAN",
        "roles": ["APPROVER"],
    }
    created = first.create(
        SensitiveToken("token-canary-not-plaintext"), identity, token_expires_in=300
    )
    assert second.get(created.session_id) is not None
    assert second.get(created.session_id).identity["tenant_id"] == "tenant-a"  # type: ignore[union-attr]

    other = second.create(
        SensitiveToken("other-token"),
        {
            "actor_id": "same-actor",
            "tenant_id": "tenant-b",
            "actor_kind": "HUMAN",
            "roles": ["AUDITOR"],
        },
        token_expires_in=300,
    )
    with connections.tenant_connection(TenantContext("tenant-a")) as connection:
        connection.execute("SELECT da_revoke_actor_sessions(%s,%s)", ("tenant-b", "same-actor"))
    assert second.get(other.session_id) is not None

    with psycopg.connect(dsn) as connection:
        row = connection.execute(
            "SELECT session_digest, token_ciphertext FROM decision_assurance_private.browser_sessions"
        ).fetchone()
    assert row is not None
    assert created.session_id not in row[0]
    assert "token-canary-not-plaintext" not in row[1]

    second.destroy(created.session_id)
    assert first.get(created.session_id) is None
    assert first.get("unguessable-wrong-session") is None

    stale = first.create(SensitiveToken("stale-token"), identity, token_expires_in=300)
    changed_policy = PostgresSessionStore(
        connections, **kwargs, required_mfa_policy_version="mfa-v2"
    )
    assert changed_policy.get(stale.session_id) is None


def test_pilot_acceptance_event_is_persisted_in_tenant_scoped_append_only_ledger() -> None:
    dsn = os.environ["DA_TEST_POSTGRES_DSN"]
    with psycopg.connect(dsn, autocommit=True) as bootstrap:
        bootstrap.execute((MIGRATIONS / "roles.sql").read_text(encoding="utf-8"))
    settings = PostgresSettings(SecretValue(dsn))
    PostgresMigrationRunner(settings, MIGRATIONS).migrate()
    event = EventEnvelope(
        "deployment.pilot-accepted",
        "1.0.0",
        f"acceptance-event-{datetime.now(timezone.utc).timestamp()}",
        datetime.now(timezone.utc),
        "tenant-a",
        "reviewer-a",
        "correlation-a",
        "deployment-evidence",
        {"deployment_id": "pilot-eu-1", "commit_sha": "a" * 40, "creator": "operator-a"},
    )
    application_dsn = _application_dsn(dsn)
    PostgresAcceptanceAudit(
        PostgresConnectionProvider(PostgresSettings(SecretValue(application_dsn)))
    ).append(event)
    with psycopg.connect(dsn) as inspection:
        row = inspection.execute(
            "SELECT tenant_id,event_json->>'event_type' "
            "FROM deployment_acceptance_events WHERE event_id = %s",
            (event.event_id,),
        ).fetchone()
    assert row == ("tenant-a", "deployment.pilot-accepted")
    with psycopg.connect(application_dsn) as application:
        application.execute(
            "SELECT set_config('decision_assurance.tenant_id', %s, false)", ("tenant-b",)
        )
        assert application.execute(
            "SELECT count(*) FROM deployment_acceptance_events WHERE event_id = %s",
            (event.event_id,),
        ).fetchone() == (0,)
    with psycopg.connect(application_dsn) as application:
        application.execute(
            "SELECT set_config('decision_assurance.tenant_id', %s, false)", ("tenant-a",)
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            application.execute(
                "UPDATE deployment_acceptance_events SET event_json = '{}' WHERE event_id = %s",
                (event.event_id,),
            )
