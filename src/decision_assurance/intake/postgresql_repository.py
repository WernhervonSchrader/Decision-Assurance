from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from ..persistence.postgresql import PostgresConnectionProvider
from ..tenancy import TenantContext
from .repository import IntakeIdempotencyConflict, IntakeIdempotencyWrite


class PostgresIntakeRepository:
    """PostgreSQL Intake adapter; each operation is one tenant-local transaction."""

    def __init__(self, connections: PostgresConnectionProvider):
        self._connections = connections

    def initialize(self) -> None:
        """Schema initialization is intentionally owned by the migration runner."""

    def put(
        self,
        tenant: TenantContext,
        intake_id: str,
        status: str,
        record: dict[str, Any],
    ) -> None:
        self._validate_identity(intake_id, record)
        with self._connections.tenant_connection(tenant) as connection:
            connection.execute(
                """
                INSERT INTO intake_records (tenant_id, intake_id, status, record_json)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id, intake_id) DO UPDATE
                SET status = excluded.status,
                    record_json = excluded.record_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (tenant.tenant_id, intake_id, status, Jsonb(record)),
            )

    def get(self, tenant: TenantContext, intake_id: str) -> dict[str, Any] | None:
        with self._connections.tenant_connection(tenant) as connection:
            row = connection.execute(
                """
                SELECT record_json FROM intake_records
                WHERE tenant_id = %s AND intake_id = %s
                """,
                (tenant.tenant_id, intake_id),
            ).fetchone()
        return None if row is None else dict(row["record_json"])

    def put_fact(
        self,
        tenant: TenantContext,
        intake_id: str,
        fact_id: str,
        fact: dict[str, Any],
    ) -> None:
        with self._connections.tenant_connection(tenant) as connection:
            connection.execute(
                """
                INSERT INTO intake_facts (tenant_id, intake_id, fact_id, fact_json)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id, intake_id, fact_id) DO UPDATE
                SET fact_json = excluded.fact_json
                """,
                (tenant.tenant_id, intake_id, fact_id, Jsonb(fact)),
            )

    def save_operation(
        self,
        tenant: TenantContext,
        intake_id: str,
        status: str,
        record: dict[str, Any],
        *,
        facts: list[dict[str, Any]],
        confirmation: dict[str, Any] | None,
        events: list[dict[str, Any]],
        idempotency: IntakeIdempotencyWrite,
    ) -> None:
        self._validate_identity(intake_id, record)
        actor_id, operation, key, request_hash, response = idempotency
        with self._connections.tenant_connection(tenant) as connection:
            connection.execute(
                """
                INSERT INTO intake_records (tenant_id, intake_id, status, record_json)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id, intake_id) DO UPDATE
                SET status = excluded.status,
                    record_json = excluded.record_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (tenant.tenant_id, intake_id, status, Jsonb(record)),
            )
            connection.execute(
                """
                SELECT intake_id FROM intake_records
                WHERE tenant_id = %s AND intake_id = %s
                FOR UPDATE
                """,
                (tenant.tenant_id, intake_id),
            )
            for fact in facts:
                connection.execute(
                    """
                    INSERT INTO intake_facts (tenant_id, intake_id, fact_id, fact_json)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (tenant_id, intake_id, fact_id) DO UPDATE
                    SET fact_json = excluded.fact_json
                    """,
                    (tenant.tenant_id, intake_id, fact["fact_id"], Jsonb(fact)),
                )
            if confirmation is not None:
                connection.execute(
                    """
                    INSERT INTO intake_confirmations (
                        tenant_id, intake_id, confirmation_id, fact_id, confirmation_json
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (tenant_id, intake_id, confirmation_id) DO NOTHING
                    """,
                    (
                        tenant.tenant_id,
                        intake_id,
                        confirmation["confirmation_id"],
                        confirmation["fact_id"],
                        Jsonb(confirmation),
                    ),
                )
            sequence_row = connection.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) AS value
                FROM intake_audit_events
                WHERE tenant_id = %s AND intake_id = %s
                """,
                (tenant.tenant_id, intake_id),
            ).fetchone()
            current_sequence = 0 if sequence_row is None else int(sequence_row["value"])
            for offset, event in enumerate(events, 1):
                connection.execute(
                    """
                    INSERT INTO intake_audit_events (
                        tenant_id, intake_id, event_id, sequence, event_json
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (tenant_id, intake_id, event_id) DO NOTHING
                    """,
                    (
                        tenant.tenant_id,
                        intake_id,
                        event["event_id"],
                        current_sequence + offset,
                        Jsonb(event),
                    ),
                )
            connection.execute(
                """
                INSERT INTO intake_idempotency (
                    tenant_id, actor_id, operation, idempotency_key,
                    request_hash, response_json
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (tenant.tenant_id, actor_id, operation, key, request_hash, Jsonb(response)),
            )

    def list_audit(self, tenant: TenantContext, intake_id: str) -> list[dict[str, Any]]:
        with self._connections.tenant_connection(tenant) as connection:
            rows = connection.execute(
                """
                SELECT event_json FROM intake_audit_events
                WHERE tenant_id = %s AND intake_id = %s
                ORDER BY sequence
                """,
                (tenant.tenant_id, intake_id),
            ).fetchall()
        return [dict(row["event_json"]) for row in rows]

    def get_idempotency(
        self,
        tenant: TenantContext,
        actor_id: str,
        operation: str,
        key: str,
        request_hash: str,
    ) -> dict[str, Any] | None:
        with self._connections.tenant_connection(tenant) as connection:
            row = connection.execute(
                """
                SELECT request_hash, response_json FROM intake_idempotency
                WHERE tenant_id = %s AND actor_id = %s
                  AND operation = %s AND idempotency_key = %s
                """,
                (tenant.tenant_id, actor_id, operation, key),
            ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise IntakeIdempotencyConflict("IDEMPOTENCY_KEY_REUSED")
        return dict(row["response_json"])

    def store_idempotency(
        self,
        tenant: TenantContext,
        actor_id: str,
        operation: str,
        key: str,
        request_hash: str,
        response: dict[str, Any],
    ) -> None:
        with self._connections.tenant_connection(tenant) as connection:
            connection.execute(
                """
                INSERT INTO intake_idempotency (
                    tenant_id, actor_id, operation, idempotency_key,
                    request_hash, response_json
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (tenant.tenant_id, actor_id, operation, key, request_hash, Jsonb(response)),
            )

    @staticmethod
    def _validate_identity(intake_id: str, record: dict[str, Any]) -> None:
        if record.get("intake_id") != intake_id:
            raise ValueError("INTAKE_ID_MISMATCH")
