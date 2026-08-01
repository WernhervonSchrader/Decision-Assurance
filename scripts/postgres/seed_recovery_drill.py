from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
from pathlib import Path

import psycopg
from cryptography.fernet import Fernet
from psycopg.types.json import Jsonb

from decision_assurance.persistence.postgresql import (
    PostgresConnectionProvider,
    PostgresSettings,
)
from decision_assurance.pilot_ui.session import SensitiveToken
from decision_assurance.pilot_ui.session_postgresql import PostgresSessionStore
from decision_assurance.production.contracts import SecretValue


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a bounded recovery drill")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--session-state", required=True, type=Path)
    arguments = parser.parse_args()
    with psycopg.connect(arguments.dsn) as connection:
        connection.execute(
            "INSERT INTO decisions (tenant_id,decision_id,document_json) VALUES "
            "(%s,%s,%s),(%s,%s,%s)",
            (
                "recovery-tenant-a",
                "recovery-decision-1",
                Jsonb({"decision_id": "recovery-decision-1", "status": "REVIEW"}),
                "recovery-tenant-b",
                "recovery-decision-2",
                Jsonb({"decision_id": "recovery-decision-2", "status": "BLOCKED"}),
            ),
        )
        for tenant, decision, event_id in (
            ("recovery-tenant-a", "recovery-decision-1", "recovery-event-1"),
            ("recovery-tenant-b", "recovery-decision-2", "recovery-event-2"),
        ):
            connection.execute(
                "INSERT INTO audit_events (tenant_id,decision_id,event_id,event_json) "
                "VALUES (%s,%s,%s,%s)",
                (
                    tenant,
                    decision,
                    event_id,
                    Jsonb(
                        {
                            "event_id": event_id,
                            "event_type": "decision.created",
                            "previous_event_hash": None,
                        }
                    ),
                ),
            )
        connection.execute(
            "INSERT INTO research_runs "
            "(tenant_id,research_run_id,decision_file_id,semantic_fingerprint,status,run_json,created_at,updated_at) "
            "VALUES (%s,%s,%s,%s,'COMPLETED',%s,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),"
            "(%s,%s,%s,%s,'COMPLETED',%s,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
            (
                "recovery-tenant-a",
                "recovery-run-1",
                "recovery-decision-1",
                "recovery-fingerprint-1",
                Jsonb({"sources": 2}),
                "recovery-tenant-b",
                "recovery-run-2",
                "recovery-decision-2",
                "recovery-fingerprint-2",
                Jsonb({"sources": 1}),
            ),
        )
    pepper = secrets.token_bytes(32)
    envelope_key = Fernet.generate_key()
    store = PostgresSessionStore(
        PostgresConnectionProvider(PostgresSettings(SecretValue(arguments.dsn))),
        session_pepper=pepper,
        envelope_key=envelope_key,
    )
    sessions = []
    for tenant, actor in (
        ("recovery-tenant-a", "recovery-actor-1"),
        ("recovery-tenant-b", "recovery-actor-2"),
    ):
        session = store.create(
            SensitiveToken("ephemeral-recovery-token"),
            {
                "tenant_id": tenant,
                "actor_id": actor,
                "actor_kind": "HUMAN",
                "roles": ["AUDITOR"],
            },
            token_expires_in=1800,
        )
        sessions.append({"session_id": session.session_id, "tenant_id": tenant})
    arguments.session_state.write_text(
        json.dumps(
            {
                "pepper": base64.b64encode(pepper).decode("ascii"),
                "envelope_key": envelope_key.decode("ascii"),
                "sessions": sessions,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    os.chmod(arguments.session_state, 0o600)


if __name__ == "__main__":
    main()
