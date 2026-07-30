from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, cast

from ..tenancy import TenantContext
from .codec import run_from_data, to_data
from .contracts import ResearchRun, SourceSnapshot


class ResearchIdempotencyConflict(ValueError):
    pass


class SqliteResearchRepository:
    """Research-owned SQLite tables; every relationship is tenant scoped."""

    def __init__(self, database_path: Path, migration_path: Path | None = None):
        self.database_path = database_path
        self.migration_path = (
            migration_path or Path(__file__).parents[1] / "migrations" / "003_web_research_v0_4.sql"
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

    def create_or_get(self, tenant: TenantContext, run: ResearchRun) -> ResearchRun:
        self._assert_tenant(tenant, run)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT run_json FROM research_runs WHERE tenant_id=? AND semantic_fingerprint=?",
                (tenant.tenant_id, run.semantic_fingerprint),
            ).fetchone()
            if row:
                return run_from_data(json.loads(row["run_json"]))
            # A successful handoff advances the stored Decision File hash. A
            # byte-identical repeat of the research request must still converge
            # to that run when the current document is exactly its handoff result.
            prior_rows = connection.execute(
                "SELECT run_json FROM research_runs WHERE tenant_id=? AND decision_file_id=?",
                (tenant.tenant_id, run.request.decision_file_id),
            ).fetchall()
            for prior_row in prior_rows:
                prior = run_from_data(json.loads(prior_row["run_json"]))
                if (
                    prior.request == run.request
                    and prior.expected_document_hash == run.expected_document_hash
                ):
                    return prior
            connection.execute(
                "INSERT INTO research_runs "
                "(tenant_id,research_run_id,decision_file_id,semantic_fingerprint,status,run_json,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    tenant.tenant_id,
                    run.research_run_id,
                    run.request.decision_file_id,
                    run.semantic_fingerprint,
                    run.status.value,
                    self._serialize(to_data(run)),
                    run.created_at,
                    run.updated_at,
                ),
            )
            connection.execute(
                "INSERT INTO research_budget_usage (tenant_id,research_run_id,used_units) VALUES (?,?,0)",
                (tenant.tenant_id, run.research_run_id),
            )
        return run

    def get(self, tenant: TenantContext, run_id: str) -> ResearchRun | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT run_json FROM research_runs WHERE tenant_id=? AND research_run_id=?",
                (tenant.tenant_id, run_id),
            ).fetchone()
        return run_from_data(json.loads(row["run_json"])) if row else None

    def save(self, tenant: TenantContext, run: ResearchRun) -> None:
        self._assert_tenant(tenant, run)
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE research_runs SET status=?,run_json=?,updated_at=? "
                "WHERE tenant_id=? AND research_run_id=?",
                (
                    run.status.value,
                    self._serialize(to_data(run)),
                    run.updated_at,
                    tenant.tenant_id,
                    run.research_run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError("RESEARCH_RUN_NOT_FOUND")
            for source in run.sources:
                connection.execute(
                    "INSERT INTO research_source_candidates "
                    "(tenant_id,research_run_id,source_id,source_json) VALUES (?,?,?,?) "
                    "ON CONFLICT (tenant_id,research_run_id,source_id) "
                    "DO UPDATE SET source_json=excluded.source_json",
                    (
                        tenant.tenant_id,
                        run.research_run_id,
                        source.source_id,
                        self._serialize(to_data(source)),
                    ),
                )
            for snapshot in run.snapshots:
                connection.execute(
                    "INSERT INTO research_source_snapshots "
                    "(tenant_id,research_run_id,snapshot_id,source_id,canonical_url,content_hash,expires_at,snapshot_json) "
                    "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT (tenant_id,research_run_id,snapshot_id) "
                    "DO UPDATE SET snapshot_json=excluded.snapshot_json,expires_at=excluded.expires_at",
                    (
                        tenant.tenant_id,
                        run.research_run_id,
                        snapshot.snapshot_id,
                        snapshot.source_id,
                        snapshot.canonical_url,
                        snapshot.content_hash,
                        snapshot.expires_at,
                        self._serialize(to_data(snapshot)),
                    ),
                )
            for evidence in run.evidence:
                connection.execute(
                    "INSERT INTO research_evidence_candidates "
                    "(tenant_id,research_run_id,evidence_id,source_id,snapshot_id,content_hash,evidence_json) "
                    "VALUES (?,?,?,?,?,?,?) ON CONFLICT (tenant_id,research_run_id,evidence_id) "
                    "DO UPDATE SET evidence_json=excluded.evidence_json",
                    (
                        tenant.tenant_id,
                        run.research_run_id,
                        evidence.evidence_id,
                        evidence.source_id,
                        evidence.snapshot_id,
                        evidence.content_hash,
                        self._serialize(to_data(evidence)),
                    ),
                )
            for attempt in run.attempts:
                connection.execute(
                    "INSERT INTO research_attempts "
                    "(tenant_id,research_run_id,attempt_id,attempt_json) VALUES (?,?,?,?) "
                    "ON CONFLICT (tenant_id,research_run_id,attempt_id) DO NOTHING",
                    (
                        tenant.tenant_id,
                        run.research_run_id,
                        attempt.attempt_id,
                        self._serialize(to_data(attempt)),
                    ),
                )
            for sequence, event in enumerate(run.audit_events, 1):
                serialized = self._serialize(to_data(event))
                existing = connection.execute(
                    "SELECT event_json FROM research_audit_events "
                    "WHERE tenant_id=? AND research_run_id=? AND event_id=?",
                    (tenant.tenant_id, run.research_run_id, event.event_id),
                ).fetchone()
                if existing and existing["event_json"] != serialized:
                    raise ValueError("AUDIT_EVENT_CONFLICT")
                connection.execute(
                    "INSERT INTO research_audit_events "
                    "(tenant_id,research_run_id,event_id,sequence,event_json) VALUES (?,?,?,?,?) "
                    "ON CONFLICT (tenant_id,research_run_id,event_id) DO NOTHING",
                    (tenant.tenant_id, run.research_run_id, event.event_id, sequence, serialized),
                )

    def list_sources(
        self, tenant: TenantContext, run_id: str, *, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        self._validate_page(limit, offset)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT source_json FROM research_source_candidates "
                "WHERE tenant_id=? AND research_run_id=? ORDER BY source_id LIMIT ? OFFSET ?",
                (tenant.tenant_id, run_id, limit, offset),
            ).fetchall()
        return [cast(dict[str, Any], json.loads(row["source_json"])) for row in rows]

    def list_evidence(
        self, tenant: TenantContext, run_id: str, *, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        self._validate_page(limit, offset)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT evidence_json FROM research_evidence_candidates "
                "WHERE tenant_id=? AND research_run_id=? ORDER BY evidence_id LIMIT ? OFFSET ?",
                (tenant.tenant_id, run_id, limit, offset),
            ).fetchall()
        return [cast(dict[str, Any], json.loads(row["evidence_json"])) for row in rows]

    def list_audit(self, tenant: TenantContext, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_json FROM research_audit_events "
                "WHERE tenant_id=? AND research_run_id=? ORDER BY sequence",
                (tenant.tenant_id, run_id),
            ).fetchall()
        return [cast(dict[str, Any], json.loads(row["event_json"])) for row in rows]

    def get_snapshot(
        self, tenant: TenantContext, canonical_url: str, *, current_time: str
    ) -> SourceSnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT snapshot_json FROM research_source_snapshots "
                "WHERE tenant_id=? AND canonical_url=? AND expires_at>? "
                "ORDER BY expires_at DESC LIMIT 1",
                (tenant.tenant_id, canonical_url, current_time),
            ).fetchone()
        if not row:
            return None
        raw = cast(dict[str, Any], json.loads(row["snapshot_json"]))
        from .contracts import ContentRisk  # avoid a module-level codec cycle

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
        with self._connect() as connection:
            row = connection.execute(
                "SELECT used_units FROM research_budget_usage "
                "WHERE tenant_id=? AND research_run_id=?",
                (tenant.tenant_id, run_id),
            ).fetchone()
            if row is None:
                raise KeyError("RESEARCH_RUN_NOT_FOUND")
            used = int(row["used_units"])
            if used >= limit:
                raise ValueError("BUDGET_EXCEEDED")
            used += 1
            connection.execute(
                "UPDATE research_budget_usage SET used_units=?,updated_at=CURRENT_TIMESTAMP "
                "WHERE tenant_id=? AND research_run_id=?",
                (used, tenant.tenant_id, run_id),
            )
        return used

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
            connection.execute(
                "INSERT INTO research_idempotency "
                "(tenant_id,actor_id,operation,idempotency_key,request_hash,status_code,response_json) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    tenant.tenant_id,
                    actor_id,
                    operation,
                    key,
                    request_hash,
                    status_code,
                    self._serialize(response),
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
        with self._connect() as connection:
            row = connection.execute(
                "SELECT request_hash,status_code,response_json FROM research_idempotency "
                "WHERE tenant_id=? AND actor_id=? AND operation=? AND idempotency_key=?",
                (tenant.tenant_id, actor_id, operation, key),
            ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise ResearchIdempotencyConflict("IDEMPOTENCY_KEY_REUSED")
        return int(row["status_code"]), cast(dict[str, Any], json.loads(row["response_json"]))

    @staticmethod
    def _assert_tenant(tenant: TenantContext, run: ResearchRun) -> None:
        if tenant.tenant_id != run.tenant_id:
            raise ValueError("TENANT_MISMATCH")

    @staticmethod
    def _serialize(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _validate_page(limit: int, offset: int) -> None:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("INVALID_PAGE_LIMIT")
