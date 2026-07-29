from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..tenancy import TenantContext
from .protocols import IdempotencyWrite


class IdempotencyConflict(ValueError):
    pass


class SqliteDecisionRepository:
    def __init__(self, database_path: Path, migration_path: Path | None = None):
        self.database_path = database_path
        self.migration_path = (
            migration_path or Path(__file__).parents[1] / "migrations" / "001_api_v0_2.sql"
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(self.migration_path.read_text(encoding="utf-8"))

    def ready(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def create_decision(
        self,
        tenant: TenantContext,
        document: dict[str, Any],
        events: list[dict[str, Any]] | None = None,
        idempotency: IdempotencyWrite | None = None,
    ) -> None:
        serialized = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO decisions (tenant_id, decision_id, document_json) VALUES (?, ?, ?)",
                (tenant.tenant_id, document["decision_id"], serialized),
            )
            for event in events or []:
                self._insert_audit(connection, tenant, document["decision_id"], event)
            if idempotency:
                self._insert_idempotency(connection, tenant, idempotency)

    def get_decision(self, tenant: TenantContext, decision_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT document_json FROM decisions WHERE tenant_id = ? AND decision_id = ?",
                (tenant.tenant_id, decision_id),
            ).fetchone()
        return json.loads(row["document_json"]) if row else None

    def save_result(
        self,
        tenant: TenantContext,
        document: dict[str, Any],
        report: dict[str, Any] | None,
        events: list[dict[str, Any]],
        idempotency: IdempotencyWrite | None = None,
    ) -> None:
        decision_id = document["decision_id"]
        document_json = json.dumps(
            document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE decisions SET document_json = ?, updated_at = CURRENT_TIMESTAMP WHERE tenant_id = ? AND decision_id = ?",
                (document_json, tenant.tenant_id, decision_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("DECISION_NOT_FOUND")
            if report is not None:
                report_json = json.dumps(
                    report, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                )
                connection.execute(
                    "INSERT INTO reports (tenant_id, decision_id, report_json) VALUES (?, ?, ?) ON CONFLICT (tenant_id, decision_id) DO UPDATE SET report_json = excluded.report_json, created_at = CURRENT_TIMESTAMP",
                    (tenant.tenant_id, decision_id, report_json),
                )
            for event in events:
                self._insert_audit(connection, tenant, decision_id, event)
            if idempotency:
                self._insert_idempotency(connection, tenant, idempotency)

    @staticmethod
    def _insert_audit(
        connection: sqlite3.Connection,
        tenant: TenantContext,
        decision_id: str,
        event: dict[str, Any],
    ) -> None:
        connection.execute(
            "INSERT INTO audit_events (tenant_id, decision_id, event_id, event_json) VALUES (?, ?, ?, ?)",
            (
                tenant.tenant_id,
                decision_id,
                event["event_id"],
                json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            ),
        )

    @staticmethod
    def _insert_idempotency(
        connection: sqlite3.Connection,
        tenant: TenantContext,
        write: IdempotencyWrite,
    ) -> None:
        actor_id, operation, key, request_hash, status_code, response = write
        connection.execute(
            "INSERT INTO idempotency (tenant_id, actor_id, operation, idempotency_key, request_hash, status_code, response_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                tenant.tenant_id,
                actor_id,
                operation,
                key,
                request_hash,
                status_code,
                json.dumps(response, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            ),
        )

    def get_report(self, tenant: TenantContext, decision_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT report_json FROM reports WHERE tenant_id = ? AND decision_id = ?",
                (tenant.tenant_id, decision_id),
            ).fetchone()
        return json.loads(row["report_json"]) if row else None

    def list_audit(
        self, tenant: TenantContext, decision_id: str, *, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("INVALID_PAGE_LIMIT")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_json FROM audit_events WHERE tenant_id = ? AND decision_id = ? ORDER BY sequence LIMIT ? OFFSET ?",
                (tenant.tenant_id, decision_id, limit, offset),
            ).fetchall()
        return [json.loads(row["event_json"]) for row in rows]

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
        with self._connect() as connection:
            self._insert_idempotency(
                connection,
                tenant,
                (actor_id, operation, key, request_hash, status_code, response),
            )

    def get_idempotency(
        self, tenant: TenantContext, actor_id: str, operation: str, key: str, request_hash: str
    ) -> tuple[int, dict[str, Any]] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT request_hash, status_code, response_json FROM idempotency WHERE tenant_id = ? AND actor_id = ? AND operation = ? AND idempotency_key = ?",
                (tenant.tenant_id, actor_id, operation, key),
            ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise IdempotencyConflict("IDEMPOTENCY_KEY_REUSED")
        return row["status_code"], json.loads(row["response_json"])
