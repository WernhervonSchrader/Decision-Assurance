from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from ..persistence.postgresql import PostgresConnectionProvider
from ..tenancy import TenantContext
from .protocols import IdempotencyWrite
from .sqlite import IdempotencyConflict


class PostgresDecisionRepository:
    """Decision persistence with transaction-local tenant context and database RLS."""

    def __init__(self, connections: PostgresConnectionProvider):
        self._connections = connections

    def initialize(self) -> None:
        """Schema initialization is intentionally owned by the migration runner."""

    def ready(self) -> bool:
        return self._connections.ready()

    def create_decision(
        self,
        tenant: TenantContext,
        document: dict[str, Any],
        events: list[dict[str, Any]] | None = None,
        idempotency: IdempotencyWrite | None = None,
    ) -> None:
        with self._connections.tenant_connection(tenant) as connection:
            connection.execute(
                """
                INSERT INTO decisions (tenant_id, decision_id, document_json)
                VALUES (%s, %s, %s)
                """,
                (tenant.tenant_id, document["decision_id"], Jsonb(document)),
            )
            for event in events or []:
                self._insert_audit(connection, tenant, str(document["decision_id"]), event)
            if idempotency:
                self._insert_idempotency(connection, tenant, idempotency)

    def get_decision(self, tenant: TenantContext, decision_id: str) -> dict[str, Any] | None:
        with self._connections.tenant_connection(tenant) as connection:
            row = connection.execute(
                """
                SELECT document_json
                FROM decisions
                WHERE tenant_id = %s AND decision_id = %s
                """,
                (tenant.tenant_id, decision_id),
            ).fetchone()
        return None if row is None else dict(row["document_json"])

    def save_result(
        self,
        tenant: TenantContext,
        document: dict[str, Any],
        report: dict[str, Any] | None,
        events: list[dict[str, Any]],
        idempotency: IdempotencyWrite | None = None,
    ) -> None:
        decision_id = str(document["decision_id"])
        with self._connections.tenant_connection(tenant) as connection:
            cursor = connection.execute(
                """
                UPDATE decisions
                SET document_json = %s, updated_at = CURRENT_TIMESTAMP
                WHERE tenant_id = %s AND decision_id = %s
                """,
                (Jsonb(document), tenant.tenant_id, decision_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("DECISION_NOT_FOUND")
            if report is not None:
                connection.execute(
                    """
                    INSERT INTO reports (tenant_id, decision_id, report_json)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (tenant_id, decision_id) DO UPDATE
                    SET report_json = excluded.report_json, created_at = CURRENT_TIMESTAMP
                    """,
                    (tenant.tenant_id, decision_id, Jsonb(report)),
                )
            for event in events:
                self._insert_audit(connection, tenant, decision_id, event)
            if idempotency:
                self._insert_idempotency(connection, tenant, idempotency)

    @staticmethod
    def _insert_audit(
        connection: Connection[dict[str, Any]],
        tenant: TenantContext,
        decision_id: str,
        event: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_events (tenant_id, decision_id, event_id, event_json)
            VALUES (%s, %s, %s, %s)
            """,
            (tenant.tenant_id, decision_id, event["event_id"], Jsonb(event)),
        )

    @staticmethod
    def _insert_idempotency(
        connection: Connection[dict[str, Any]],
        tenant: TenantContext,
        write: IdempotencyWrite,
    ) -> None:
        actor_id, operation, key, request_hash, status_code, response = write
        connection.execute(
            """
            INSERT INTO idempotency (
                tenant_id, actor_id, operation, idempotency_key,
                request_hash, status_code, response_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tenant.tenant_id,
                actor_id,
                operation,
                key,
                request_hash,
                status_code,
                Jsonb(response),
            ),
        )

    def get_report(self, tenant: TenantContext, decision_id: str) -> dict[str, Any] | None:
        with self._connections.tenant_connection(tenant) as connection:
            row = connection.execute(
                """
                SELECT report_json
                FROM reports
                WHERE tenant_id = %s AND decision_id = %s
                """,
                (tenant.tenant_id, decision_id),
            ).fetchone()
        return None if row is None else dict(row["report_json"])

    def list_audit(
        self, tenant: TenantContext, decision_id: str, *, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("INVALID_PAGE_LIMIT")
        with self._connections.tenant_connection(tenant) as connection:
            rows = connection.execute(
                """
                SELECT event_json
                FROM audit_events
                WHERE tenant_id = %s AND decision_id = %s
                ORDER BY sequence
                LIMIT %s OFFSET %s
                """,
                (tenant.tenant_id, decision_id, limit, offset),
            ).fetchall()
        return [dict(row["event_json"]) for row in rows]

    def store_idempotency(
        self,
        tenant: TenantContext,
        actor_id: str,
        operation: str,
        key: str,
        request_hash: str,
        status_code: int,
        response: dict[str, Any],
    ) -> None:
        with self._connections.tenant_connection(tenant) as connection:
            self._insert_idempotency(
                connection,
                tenant,
                (actor_id, operation, key, request_hash, status_code, response),
            )

    def get_idempotency(
        self,
        tenant: TenantContext,
        actor_id: str,
        operation: str,
        key: str,
        request_hash: str,
    ) -> tuple[int, dict[str, Any]] | None:
        with self._connections.tenant_connection(tenant) as connection:
            row = connection.execute(
                """
                SELECT request_hash, status_code, response_json
                FROM idempotency
                WHERE tenant_id = %s AND actor_id = %s
                  AND operation = %s AND idempotency_key = %s
                """,
                (tenant.tenant_id, actor_id, operation, key),
            ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise IdempotencyConflict("IDEMPOTENCY_KEY_REUSED")
        return int(row["status_code"]), dict(row["response_json"])
