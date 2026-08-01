from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ..persistence.postgresql import PostgresConnectionProvider
from ..tenancy import TenantContext
from .contracts import DeletionRequest, DeletionStatus, LifecycleEvent
from .ports import LegalHoldActive


class PostgresLifecycleRepository:
    def __init__(self, connections: PostgresConnectionProvider):
        self._connections = connections

    def case_exists(self, tenant: TenantContext, decision_id: str) -> bool:
        with self._connections.tenant_connection(tenant) as connection:
            row = connection.execute(
                "SELECT 1 FROM decisions WHERE tenant_id = %s AND decision_id = %s",
                (tenant.tenant_id, decision_id),
            ).fetchone()
        return row is not None

    def get_by_idempotency(
        self, tenant: TenantContext, actor_hash: str, key_hash: str
    ) -> DeletionRequest | None:
        with self._connections.tenant_connection(tenant) as connection:
            row = connection.execute(
                """
                SELECT * FROM deletion_requests
                WHERE tenant_id = %s AND actor_hash = %s AND idempotency_key_hash = %s
                """,
                (tenant.tenant_id, actor_hash, key_hash),
            ).fetchone()
        return None if row is None else _request(row, self.last_event(tenant, row["request_id"]))

    def get_request(self, tenant: TenantContext, request_id: str) -> DeletionRequest | None:
        with self._connections.tenant_connection(tenant) as connection:
            row = connection.execute(
                "SELECT * FROM deletion_requests WHERE tenant_id = %s AND request_id = %s",
                (tenant.tenant_id, request_id),
            ).fetchone()
        return None if row is None else _request(row, self.last_event(tenant, request_id))

    def persist_transition(self, request: DeletionRequest, event: LifecycleEvent) -> None:
        tenant = TenantContext(request.tenant_id)
        with self._connections.tenant_connection(tenant) as connection:
            connection.execute(
                """
                INSERT INTO deletion_requests
                    (tenant_id, request_id, decision_id, case_ref_hash, actor_hash,
                     idempotency_key_hash, status, reason_code, requested_at, completed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, request_id) DO UPDATE SET
                    decision_id = EXCLUDED.decision_id,
                    status = EXCLUDED.status,
                    completed_at = EXCLUDED.completed_at
                """,
                (
                    request.tenant_id,
                    request.request_id,
                    request.decision_id,
                    request.case_ref_hash,
                    request.actor_hash,
                    request.idempotency_key_hash,
                    request.status.value,
                    request.reason_code,
                    request.requested_at,
                    request.completed_at,
                ),
            )
            self._append_event(connection, event)

    def active_hold(self, tenant: TenantContext, decision_id: str) -> bool:
        with self._connections.tenant_connection(tenant) as connection:
            row = connection.execute(
                """
                SELECT 1 FROM legal_holds
                WHERE tenant_id = %s AND decision_id = %s AND active
                """,
                (tenant.tenant_id, decision_id),
            ).fetchone()
        return row is not None

    def set_hold(
        self,
        tenant: TenantContext,
        decision_id: str,
        hold_id: str,
        actor_hash: str,
        reason_code: str,
        occurred_at: str,
    ) -> None:
        with self._connections.tenant_connection(tenant) as connection:
            _lock_case(connection, tenant.tenant_id, decision_id)
            existing = connection.execute(
                """
                SELECT 1 FROM legal_holds
                WHERE tenant_id = %s AND decision_id = %s AND active
                """,
                (tenant.tenant_id, decision_id),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO legal_holds
                        (tenant_id, decision_id, hold_id, reason_code,
                         created_by_actor_hash, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        tenant.tenant_id,
                        decision_id,
                        hold_id,
                        reason_code,
                        actor_hash,
                        occurred_at,
                    ),
                )

    def release_hold(
        self, tenant: TenantContext, decision_id: str, actor_hash: str, occurred_at: str
    ) -> bool:
        with self._connections.tenant_connection(tenant) as connection:
            _lock_case(connection, tenant.tenant_id, decision_id)
            cursor = connection.execute(
                """
                UPDATE legal_holds SET active = FALSE, released_by_actor_hash = %s,
                    released_at = %s
                WHERE tenant_id = %s AND decision_id = %s AND active
                """,
                (actor_hash, occurred_at, tenant.tenant_id, decision_id),
            )
            return cursor.rowcount > 0

    @staticmethod
    def _append_event(connection: Any, event: LifecycleEvent) -> None:
        connection.execute(
            """
                INSERT INTO lifecycle_audit_events
                    (tenant_id, event_id, request_id, case_ref_hash, event_type,
                     event_json, event_hash, previous_event_hash, occurred_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
            (
                event.tenant_id,
                event.event_id,
                event.request_id,
                event.case_ref_hash,
                event.event_type,
                Jsonb(event.payload()),
                event.event_hash,
                event.previous_event_hash,
                event.occurred_at,
            ),
        )

    def last_event(self, tenant: TenantContext, request_id: str) -> LifecycleEvent | None:
        with self._connections.tenant_connection(tenant) as connection:
            row = connection.execute(
                """
                SELECT event_json, event_hash, previous_event_hash
                FROM lifecycle_audit_events
                WHERE tenant_id = %s AND request_id = %s
                ORDER BY sequence DESC LIMIT 1
                """,
                (tenant.tenant_id, request_id),
            ).fetchone()
        if row is None:
            return None
        value = dict(row["event_json"])
        return LifecycleEvent(
            tenant_id=tenant.tenant_id,
            event_id=value["event_id"],
            request_id=value["request_id"],
            case_ref_hash=value["case_ref_hash"],
            event_type=value["event_type"],
            occurred_at=value["occurred_at"],
            reason_code=value["reason_code"],
            correlation_id=value["correlation_id"],
            actor_hash=value["actor_hash"],
            event_hash=row["event_hash"],
            previous_event_hash=row["previous_event_hash"],
        )

    def delete_case_data(self, tenant: TenantContext, decision_id: str) -> None:
        with self._connections.tenant_connection(tenant) as connection:
            _lock_case(connection, tenant.tenant_id, decision_id)
            held = connection.execute(
                """
                SELECT 1 FROM legal_holds
                WHERE tenant_id = %s AND decision_id = %s AND active
                """,
                (tenant.tenant_id, decision_id),
            ).fetchone()
            if held is not None:
                raise LegalHoldActive("LEGAL_HOLD_ACTIVE")
            parameters = (tenant.tenant_id, decision_id)
            connection.execute(
                """
                DELETE FROM research_job_events WHERE tenant_id = %s AND job_id IN
                    (SELECT job_id FROM research_jobs WHERE tenant_id = %s AND research_run_id IN
                        (SELECT research_run_id FROM research_runs
                         WHERE tenant_id = %s AND decision_file_id = %s))
                """,
                (tenant.tenant_id, tenant.tenant_id, *parameters),
            )
            connection.execute(
                """
                DELETE FROM research_jobs WHERE tenant_id = %s AND research_run_id IN
                    (SELECT research_run_id FROM research_runs
                     WHERE tenant_id = %s AND decision_file_id = %s)
                """,
                (tenant.tenant_id, *parameters),
            )
            for table in (
                "research_handoffs",
                "research_evidence_candidates",
                "research_source_snapshots",
                "research_source_candidates",
                "research_attempts",
                "research_audit_events",
                "research_budget_usage",
            ):
                connection.execute(
                    psycopg.sql.SQL(
                        "DELETE FROM {} WHERE tenant_id = %s AND research_run_id IN "
                        "(SELECT research_run_id FROM research_runs "
                        "WHERE tenant_id = %s AND decision_file_id = %s)"
                    ).format(psycopg.sql.Identifier(table)),
                    (tenant.tenant_id, *parameters),
                )
            connection.execute(
                "DELETE FROM research_idempotency WHERE tenant_id = %s AND "
                "(response_json ->> 'decision_file_id' = %s OR operation LIKE %s)",
                (tenant.tenant_id, decision_id, f"%:{decision_id}%"),
            )
            connection.execute(
                "DELETE FROM research_runs WHERE tenant_id = %s AND decision_file_id = %s",
                parameters,
            )
            intake_rows = connection.execute(
                """
                SELECT intake_id FROM intake_records
                WHERE tenant_id = %s AND
                    (record_json ->> 'compiled_decision_id' = %s OR intake_id || '-decision' = %s)
                """,
                (tenant.tenant_id, decision_id, decision_id),
            ).fetchall()
            intake_ids = [row["intake_id"] for row in intake_rows]
            if intake_ids:
                for table in (
                    "intake_confirmations",
                    "intake_facts",
                    "intake_audit_events",
                ):
                    connection.execute(
                        psycopg.sql.SQL(
                            "DELETE FROM {} WHERE tenant_id = %s AND intake_id = ANY(%s)"
                        ).format(psycopg.sql.Identifier(table)),
                        (tenant.tenant_id, intake_ids),
                    )
                connection.execute(
                    "DELETE FROM intake_idempotency WHERE tenant_id = %s AND "
                    "(response_json ->> 'decision_id' = %s OR "
                    " response_json ->> 'compiled_decision_id' = %s)",
                    (tenant.tenant_id, decision_id, decision_id),
                )
                connection.execute(
                    "DELETE FROM intake_records WHERE tenant_id = %s AND intake_id = ANY(%s)",
                    (tenant.tenant_id, intake_ids),
                )
            connection.execute(
                "DELETE FROM legal_holds WHERE tenant_id = %s AND decision_id = %s",
                parameters,
            )
            connection.execute(
                "DELETE FROM reports WHERE tenant_id = %s AND decision_id = %s", parameters
            )
            connection.execute(
                "DELETE FROM audit_events WHERE tenant_id = %s AND decision_id = %s", parameters
            )
            connection.execute(
                "DELETE FROM idempotency WHERE tenant_id = %s AND operation LIKE %s",
                (tenant.tenant_id, f"%:{decision_id}%"),
            )
            cursor = connection.execute(
                "DELETE FROM decisions WHERE tenant_id = %s AND decision_id = %s", parameters
            )
            if cursor.rowcount != 1:
                raise KeyError("CASE_NOT_FOUND")


def _lock_case(connection: Any, tenant_id: str, decision_id: str) -> None:
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"{tenant_id}\x1f{decision_id}",),
    )


def _request(row: dict[str, Any], event: LifecycleEvent | None) -> DeletionRequest:
    return DeletionRequest(
        tenant_id=row["tenant_id"],
        request_id=row["request_id"],
        decision_id=row["decision_id"],
        case_ref_hash=row["case_ref_hash"],
        actor_hash=row["actor_hash"],
        idempotency_key_hash=row["idempotency_key_hash"],
        status=DeletionStatus(row["status"]),
        reason_code=row["reason_code"],
        requested_at=row["requested_at"].isoformat(),
        completed_at=None if row["completed_at"] is None else row["completed_at"].isoformat(),
        legal_hold_active=row["status"] == DeletionStatus.BLOCKED_BY_HOLD.value,
        event_hash="" if event is None else event.event_hash,
        previous_event_hash=None if event is None else event.previous_event_hash,
    )
