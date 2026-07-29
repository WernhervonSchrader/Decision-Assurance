from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Protocol

from ..tenancy import TenantContext


class IntakeRepository(Protocol):
    def put(
        self,
        tenant: TenantContext,
        intake_id: str,
        status: str,
        record: dict[str, Any],
    ) -> None: ...

    def get(self, tenant: TenantContext, intake_id: str) -> dict[str, Any] | None: ...


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

    @staticmethod
    def _serialize(value: dict[str, Any]) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
