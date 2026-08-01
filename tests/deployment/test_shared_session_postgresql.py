from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest
from cryptography.fernet import Fernet

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


def test_two_bff_instances_share_and_revoke_encrypted_session() -> None:
    dsn = os.environ["DA_TEST_POSTGRES_DSN"]
    with psycopg.connect(dsn, autocommit=True) as bootstrap:
        bootstrap.execute((MIGRATIONS / "roles.sql").read_text(encoding="utf-8"))
    settings = PostgresSettings(SecretValue(dsn))
    PostgresMigrationRunner(settings, MIGRATIONS).migrate()
    connections = PostgresConnectionProvider(settings)

    def clock() -> datetime:
        return datetime.now(timezone.utc)

    kwargs = {
        "session_pepper": b"p" * 32,
        "envelope_key": Fernet.generate_key(),
        "clock": clock,
    }
    first = PostgresSessionStore(connections, **kwargs)
    second = PostgresSessionStore(connections, **kwargs)
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
