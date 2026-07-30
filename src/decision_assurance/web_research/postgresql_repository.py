from __future__ import annotations

from typing import Any, cast

from psycopg.types.json import Jsonb

from ..persistence.postgresql import PostgresConnectionProvider
from ..tenancy import TenantContext
from .codec import run_from_data, to_data
from .contracts import ContentRisk, ResearchRun, SourceSnapshot
from .repository import (
    IDEMPOTENCY_IN_PROGRESS_RESPONSE,
    IDEMPOTENCY_IN_PROGRESS_STATUS,
    ResearchIdempotencyConflict,
    ResearchIdempotencyInProgress,
)


class PostgresResearchRepository:
    """Transaction-safe PostgreSQL adapter for Research-owned records."""

    def __init__(self, connections: PostgresConnectionProvider):
        self._connections = connections

    def initialize(self) -> None:
        """Schema initialization is intentionally owned by the migration runner."""

    def create_or_get(self, tenant: TenantContext, run: ResearchRun) -> ResearchRun:
        self._assert_tenant(tenant, run)
        with self._connections.tenant_connection(tenant) as connection:
            row = connection.execute(
                """
                SELECT run_json FROM research_runs
                WHERE tenant_id = %s AND semantic_fingerprint = %s
                """,
                (tenant.tenant_id, run.semantic_fingerprint),
            ).fetchone()
            if row is not None:
                return run_from_data(dict(row["run_json"]))
            prior_rows = connection.execute(
                """
                SELECT run_json FROM research_runs
                WHERE tenant_id = %s AND decision_file_id = %s
                """,
                (tenant.tenant_id, run.request.decision_file_id),
            ).fetchall()
            for prior_row in prior_rows:
                prior = run_from_data(dict(prior_row["run_json"]))
                if (
                    prior.request == run.request
                    and prior.expected_document_hash == run.expected_document_hash
                ):
                    return prior
            inserted = connection.execute(
                """
                INSERT INTO research_runs (
                    tenant_id, research_run_id, decision_file_id, semantic_fingerprint,
                    status, run_json, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, semantic_fingerprint) DO NOTHING
                """,
                (
                    tenant.tenant_id,
                    run.research_run_id,
                    run.request.decision_file_id,
                    run.semantic_fingerprint,
                    run.status.value,
                    Jsonb(to_data(run)),
                    run.created_at,
                    run.updated_at,
                ),
            )
            if inserted.rowcount == 1:
                connection.execute(
                    """
                    INSERT INTO research_budget_usage
                        (tenant_id, research_run_id, used_units)
                    VALUES (%s, %s, 0)
                    """,
                    (tenant.tenant_id, run.research_run_id),
                )
                return run
            winner = connection.execute(
                """
                SELECT run_json FROM research_runs
                WHERE tenant_id = %s AND semantic_fingerprint = %s
                """,
                (tenant.tenant_id, run.semantic_fingerprint),
            ).fetchone()
            if winner is None:
                raise RuntimeError("RESEARCH_CREATE_CONVERGENCE_FAILED")
            return run_from_data(dict(winner["run_json"]))

    def get(self, tenant: TenantContext, run_id: str) -> ResearchRun | None:
        with self._connections.tenant_connection(tenant) as connection:
            row = connection.execute(
                """
                SELECT run_json FROM research_runs
                WHERE tenant_id = %s AND research_run_id = %s
                """,
                (tenant.tenant_id, run_id),
            ).fetchone()
        return None if row is None else run_from_data(dict(row["run_json"]))

    def save(self, tenant: TenantContext, run: ResearchRun) -> None:
        self._assert_tenant(tenant, run)
        with self._connections.tenant_connection(tenant) as connection:
            cursor = connection.execute(
                """
                UPDATE research_runs
                SET status = %s, run_json = %s, updated_at = %s
                WHERE tenant_id = %s AND research_run_id = %s
                """,
                (
                    run.status.value,
                    Jsonb(to_data(run)),
                    run.updated_at,
                    tenant.tenant_id,
                    run.research_run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError("RESEARCH_RUN_NOT_FOUND")
            for source in run.sources:
                connection.execute(
                    """
                    INSERT INTO research_source_candidates (
                        tenant_id, research_run_id, source_id, source_json
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (tenant_id, research_run_id, source_id) DO UPDATE
                    SET source_json = excluded.source_json
                    """,
                    (
                        tenant.tenant_id,
                        run.research_run_id,
                        source.source_id,
                        Jsonb(to_data(source)),
                    ),
                )
            for snapshot in run.snapshots:
                connection.execute(
                    """
                    INSERT INTO research_source_snapshots (
                        tenant_id, research_run_id, snapshot_id, source_id,
                        canonical_url, content_hash, expires_at, snapshot_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (tenant_id, research_run_id, snapshot_id) DO UPDATE
                    SET snapshot_json = excluded.snapshot_json,
                        expires_at = excluded.expires_at
                    """,
                    (
                        tenant.tenant_id,
                        run.research_run_id,
                        snapshot.snapshot_id,
                        snapshot.source_id,
                        snapshot.canonical_url,
                        snapshot.content_hash,
                        snapshot.expires_at,
                        Jsonb(to_data(snapshot)),
                    ),
                )
            for evidence in run.evidence:
                connection.execute(
                    """
                    INSERT INTO research_evidence_candidates (
                        tenant_id, research_run_id, evidence_id, source_id,
                        snapshot_id, content_hash, evidence_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (tenant_id, research_run_id, evidence_id) DO UPDATE
                    SET evidence_json = excluded.evidence_json
                    """,
                    (
                        tenant.tenant_id,
                        run.research_run_id,
                        evidence.evidence_id,
                        evidence.source_id,
                        evidence.snapshot_id,
                        evidence.content_hash,
                        Jsonb(to_data(evidence)),
                    ),
                )
            for attempt in run.attempts:
                connection.execute(
                    """
                    INSERT INTO research_attempts (
                        tenant_id, research_run_id, attempt_id, attempt_json
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (tenant_id, research_run_id, attempt_id) DO NOTHING
                    """,
                    (
                        tenant.tenant_id,
                        run.research_run_id,
                        attempt.attempt_id,
                        Jsonb(to_data(attempt)),
                    ),
                )
            for sequence, event in enumerate(run.audit_events, 1):
                event_data = cast(dict[str, Any], to_data(event))
                existing = connection.execute(
                    """
                    SELECT event_json FROM research_audit_events
                    WHERE tenant_id = %s AND research_run_id = %s AND event_id = %s
                    """,
                    (tenant.tenant_id, run.research_run_id, event.event_id),
                ).fetchone()
                if existing is not None and existing["event_json"] != event_data:
                    raise ValueError("AUDIT_EVENT_CONFLICT")
                connection.execute(
                    """
                    INSERT INTO research_audit_events (
                        tenant_id, research_run_id, event_id, sequence, event_json
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (tenant_id, research_run_id, event_id) DO NOTHING
                    """,
                    (
                        tenant.tenant_id,
                        run.research_run_id,
                        event.event_id,
                        sequence,
                        Jsonb(event_data),
                    ),
                )

    def list_sources(
        self, tenant: TenantContext, run_id: str, *, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        self._validate_page(limit, offset)
        with self._connections.tenant_connection(tenant) as connection:
            rows = connection.execute(
                """
                SELECT source_json FROM research_source_candidates
                WHERE tenant_id = %s AND research_run_id = %s
                ORDER BY source_id LIMIT %s OFFSET %s
                """,
                (tenant.tenant_id, run_id, limit, offset),
            ).fetchall()
        return [dict(row["source_json"]) for row in rows]

    def list_evidence(
        self, tenant: TenantContext, run_id: str, *, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        self._validate_page(limit, offset)
        with self._connections.tenant_connection(tenant) as connection:
            rows = connection.execute(
                """
                SELECT evidence_json FROM research_evidence_candidates
                WHERE tenant_id = %s AND research_run_id = %s
                ORDER BY evidence_id LIMIT %s OFFSET %s
                """,
                (tenant.tenant_id, run_id, limit, offset),
            ).fetchall()
        return [dict(row["evidence_json"]) for row in rows]

    def list_audit(self, tenant: TenantContext, run_id: str) -> list[dict[str, Any]]:
        with self._connections.tenant_connection(tenant) as connection:
            rows = connection.execute(
                """
                SELECT event_json FROM research_audit_events
                WHERE tenant_id = %s AND research_run_id = %s
                ORDER BY sequence
                """,
                (tenant.tenant_id, run_id),
            ).fetchall()
        return [dict(row["event_json"]) for row in rows]

    def get_snapshot(
        self, tenant: TenantContext, canonical_url: str, *, current_time: str
    ) -> SourceSnapshot | None:
        with self._connections.tenant_connection(tenant) as connection:
            row = connection.execute(
                """
                SELECT snapshot_json FROM research_source_snapshots
                WHERE tenant_id = %s AND canonical_url = %s AND expires_at > %s
                ORDER BY expires_at DESC LIMIT 1
                """,
                (tenant.tenant_id, canonical_url, current_time),
            ).fetchone()
        if row is None:
            return None
        raw = dict(row["snapshot_json"])
        return SourceSnapshot(
            **{
                **raw,
                "risk": ContentRisk(
                    **{
                        **raw["risk"],
                        "risk_reasons": tuple(raw["risk"]["risk_reasons"]),
                    }
                ),
            }
        )

    def reserve_budget(self, tenant: TenantContext, run_id: str, *, limit: int) -> int:
        if limit < 1:
            raise ValueError("BUDGET_EXCEEDED")
        with self._connections.tenant_connection(tenant) as connection:
            row = connection.execute(
                """
                UPDATE research_budget_usage
                SET used_units = used_units + 1, updated_at = CURRENT_TIMESTAMP
                WHERE tenant_id = %s AND research_run_id = %s AND used_units < %s
                RETURNING used_units
                """,
                (tenant.tenant_id, run_id, limit),
            ).fetchone()
            if row is not None:
                return int(row["used_units"])
            exists = connection.execute(
                """
                SELECT 1 FROM research_budget_usage
                WHERE tenant_id = %s AND research_run_id = %s
                """,
                (tenant.tenant_id, run_id),
            ).fetchone()
            if exists is None:
                raise KeyError("RESEARCH_RUN_NOT_FOUND")
            raise ValueError("BUDGET_EXCEEDED")

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
            connection.execute(
                """
                INSERT INTO research_idempotency (
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

    def reserve_idempotency(
        self,
        tenant: TenantContext,
        actor_id: str,
        operation: str,
        key: str,
        request_hash: str,
    ) -> tuple[int, dict[str, Any]] | None:
        with self._connections.tenant_connection(tenant) as connection:
            inserted = connection.execute(
                """
                INSERT INTO research_idempotency (
                    tenant_id, actor_id, operation, idempotency_key,
                    request_hash, status_code, response_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, actor_id, operation, idempotency_key) DO NOTHING
                """,
                (
                    tenant.tenant_id,
                    actor_id,
                    operation,
                    key,
                    request_hash,
                    IDEMPOTENCY_IN_PROGRESS_STATUS,
                    Jsonb(IDEMPOTENCY_IN_PROGRESS_RESPONSE),
                ),
            )
            row = connection.execute(
                """
                SELECT request_hash, status_code, response_json FROM research_idempotency
                WHERE tenant_id = %s AND actor_id = %s
                  AND operation = %s AND idempotency_key = %s
                """,
                (tenant.tenant_id, actor_id, operation, key),
            ).fetchone()
        if row is None:
            raise RuntimeError("IDEMPOTENCY_RESERVATION_FAILED")
        if row["request_hash"] != request_hash:
            raise ResearchIdempotencyConflict("IDEMPOTENCY_KEY_REUSED")
        if inserted.rowcount == 1:
            return None
        if int(row["status_code"]) == IDEMPOTENCY_IN_PROGRESS_STATUS:
            raise ResearchIdempotencyInProgress("IDEMPOTENCY_REQUEST_IN_PROGRESS")
        return int(row["status_code"]), dict(row["response_json"])

    def complete_idempotency(
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
            cursor = connection.execute(
                """
                UPDATE research_idempotency
                SET status_code = %s, response_json = %s
                WHERE tenant_id = %s AND actor_id = %s
                  AND operation = %s AND idempotency_key = %s
                  AND request_hash = %s AND status_code = %s
                """,
                (
                    status_code,
                    Jsonb(response),
                    tenant.tenant_id,
                    actor_id,
                    operation,
                    key,
                    request_hash,
                    IDEMPOTENCY_IN_PROGRESS_STATUS,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("IDEMPOTENCY_COMPLETION_FAILED")

    def release_idempotency(
        self,
        tenant: TenantContext,
        actor_id: str,
        operation: str,
        key: str,
        request_hash: str,
    ) -> None:
        with self._connections.tenant_connection(tenant) as connection:
            connection.execute(
                """
                DELETE FROM research_idempotency
                WHERE tenant_id = %s AND actor_id = %s
                  AND operation = %s AND idempotency_key = %s
                  AND request_hash = %s AND status_code = %s
                """,
                (
                    tenant.tenant_id,
                    actor_id,
                    operation,
                    key,
                    request_hash,
                    IDEMPOTENCY_IN_PROGRESS_STATUS,
                ),
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
                SELECT request_hash, status_code, response_json FROM research_idempotency
                WHERE tenant_id = %s AND actor_id = %s
                  AND operation = %s AND idempotency_key = %s
                """,
                (tenant.tenant_id, actor_id, operation, key),
            ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise ResearchIdempotencyConflict("IDEMPOTENCY_KEY_REUSED")
        return int(row["status_code"]), dict(row["response_json"])

    @staticmethod
    def _assert_tenant(tenant: TenantContext, run: ResearchRun) -> None:
        if tenant.tenant_id != run.tenant_id:
            raise ValueError("TENANT_MISMATCH")

    @staticmethod
    def _validate_page(limit: int, offset: int) -> None:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("INVALID_PAGE_LIMIT")
