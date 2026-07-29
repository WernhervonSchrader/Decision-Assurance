from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Protocol, cast

from ..tenancy import TenantContext

IntakeIdempotencyWrite = tuple[str, str, str, str, dict[str, Any]]


class IntakeRepository(Protocol):
    def put(
        self,
        tenant: TenantContext,
        intake_id: str,
        status: str,
        record: dict[str, Any],
    ) -> None: ...

    def get(self, tenant: TenantContext, intake_id: str) -> dict[str, Any] | None: ...

    def get_idempotency(
        self, tenant: TenantContext, actor_id: str, operation: str, key: str, request_hash: str
    ) -> dict[str, Any] | None: ...

    def store_idempotency(
        self,
        tenant: TenantContext,
        actor_id: str,
        operation: str,
        key: str,
        request_hash: str,
        response: dict[str, Any],
    ) -> None: ...

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
    ) -> None: ...

    def list_audit(self, tenant: TenantContext, intake_id: str) -> list[dict[str, Any]]: ...


class IntakeIdempotencyConflict(ValueError):
    pass


class SqliteIntakeRepository:
    """Intake-owned tables in the shared database; all relationships include tenant."""

    def __init__(self, database_path: Path, migration_path: Path | None = None):
        self.database_path = database_path
        self.migration_path = (
            migration_path
            or Path(__file__).parents[1] / "migrations" / "002_controlled_intake_v0_3.sql"
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

    def put(
        self,
        tenant: TenantContext,
        intake_id: str,
        status: str,
        record: dict[str, Any],
    ) -> None:
        if record.get("intake_id") != intake_id:
            raise ValueError("INTAKE_ID_MISMATCH")
        serialized = self._serialize(record)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO intake_records (tenant_id,intake_id,status,record_json) VALUES (?,?,?,?) "
                "ON CONFLICT (tenant_id,intake_id) DO UPDATE SET status=excluded.status, "
                "record_json=excluded.record_json, updated_at=CURRENT_TIMESTAMP",
                (tenant.tenant_id, intake_id, status, serialized),
            )

    def get(self, tenant: TenantContext, intake_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM intake_records WHERE tenant_id=? AND intake_id=?",
                (tenant.tenant_id, intake_id),
            ).fetchone()
        return json.loads(row["record_json"]) if row else None

    def put_fact(
        self, tenant: TenantContext, intake_id: str, fact_id: str, fact: dict[str, Any]
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO intake_facts (tenant_id,intake_id,fact_id,fact_json) VALUES (?,?,?,?) "
                "ON CONFLICT (tenant_id,intake_id,fact_id) DO UPDATE SET fact_json=excluded.fact_json",
                (tenant.tenant_id, intake_id, fact_id, self._serialize(fact)),
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
        if record.get("intake_id") != intake_id:
            raise ValueError("INTAKE_ID_MISMATCH")
        actor_id, operation, key, request_hash, response = idempotency
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO intake_records (tenant_id,intake_id,status,record_json) VALUES (?,?,?,?) "
                "ON CONFLICT (tenant_id,intake_id) DO UPDATE SET status=excluded.status, "
                "record_json=excluded.record_json, updated_at=CURRENT_TIMESTAMP",
                (tenant.tenant_id, intake_id, status, self._serialize(record)),
            )
            for fact in facts:
                connection.execute(
                    "INSERT INTO intake_facts (tenant_id,intake_id,fact_id,fact_json) "
                    "VALUES (?,?,?,?) ON CONFLICT (tenant_id,intake_id,fact_id) "
                    "DO UPDATE SET fact_json=excluded.fact_json",
                    (tenant.tenant_id, intake_id, fact["fact_id"], self._serialize(fact)),
                )
            if confirmation is not None:
                connection.execute(
                    "INSERT INTO intake_confirmations "
                    "(tenant_id,intake_id,confirmation_id,fact_id,confirmation_json) "
                    "VALUES (?,?,?,?,?) ON CONFLICT (tenant_id,intake_id,confirmation_id) DO NOTHING",
                    (
                        tenant.tenant_id,
                        intake_id,
                        confirmation["confirmation_id"],
                        confirmation["fact_id"],
                        self._serialize(confirmation),
                    ),
                )
            current_sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence),0) AS value FROM intake_audit_events "
                "WHERE tenant_id=? AND intake_id=?",
                (tenant.tenant_id, intake_id),
            ).fetchone()["value"]
            for offset, event in enumerate(events, 1):
                connection.execute(
                    "INSERT INTO intake_audit_events "
                    "(tenant_id,intake_id,event_id,sequence,event_json) VALUES (?,?,?,?,?) "
                    "ON CONFLICT (tenant_id,intake_id,event_id) DO NOTHING",
                    (
                        tenant.tenant_id,
                        intake_id,
                        event["event_id"],
                        current_sequence + offset,
                        self._serialize(event),
                    ),
                )
            connection.execute(
                "INSERT INTO intake_idempotency "
                "(tenant_id,actor_id,operation,idempotency_key,request_hash,response_json) "
                "VALUES (?,?,?,?,?,?)",
                (
                    tenant.tenant_id,
                    actor_id,
                    operation,
                    key,
                    request_hash,
                    self._serialize(response),
                ),
            )

    def list_audit(self, tenant: TenantContext, intake_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_json FROM intake_audit_events WHERE tenant_id=? AND intake_id=? "
                "ORDER BY sequence",
                (tenant.tenant_id, intake_id),
            ).fetchall()
        return [cast(dict[str, Any], json.loads(row["event_json"])) for row in rows]

    def get_idempotency(
        self, tenant: TenantContext, actor_id: str, operation: str, key: str, request_hash: str
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT request_hash,response_json FROM intake_idempotency "
                "WHERE tenant_id=? AND actor_id=? AND operation=? AND idempotency_key=?",
                (tenant.tenant_id, actor_id, operation, key),
            ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise IntakeIdempotencyConflict("IDEMPOTENCY_KEY_REUSED")
        return cast(dict[str, Any], json.loads(row["response_json"]))

    def store_idempotency(
        self,
        tenant: TenantContext,
        actor_id: str,
        operation: str,
        key: str,
        request_hash: str,
        response: dict[str, Any],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO intake_idempotency "
                "(tenant_id,actor_id,operation,idempotency_key,request_hash,response_json) "
                "VALUES (?,?,?,?,?,?)",
                (
                    tenant.tenant_id,
                    actor_id,
                    operation,
                    key,
                    request_hash,
                    self._serialize(response),
                ),
            )

    @staticmethod
    def _serialize(value: dict[str, Any]) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
