from __future__ import annotations

from typing import Any

from ..persistence.postgresql import PostgresConnectionProvider
from ..tenancy import TenantContext


class PostgresExportRepository:
    """Builds one tenant-scoped, transactionally consistent export snapshot."""

    def __init__(self, connections: PostgresConnectionProvider):
        self._connections = connections

    def snapshot(self, tenant: TenantContext, decision_id: str) -> dict[str, Any] | None:
        with self._connections.tenant_snapshot_connection(tenant) as connection:
            decision = connection.execute(
                "SELECT document_json FROM decisions WHERE tenant_id = %s AND decision_id = %s",
                (tenant.tenant_id, decision_id),
            ).fetchone()
            if decision is None:
                return None
            report = connection.execute(
                "SELECT report_json FROM reports WHERE tenant_id = %s AND decision_id = %s",
                (tenant.tenant_id, decision_id),
            ).fetchone()
            intake_records = connection.execute(
                """
                SELECT record_json FROM intake_records
                WHERE tenant_id = %s AND
                    (record_json ->> 'compiled_decision_id' = %s OR intake_id || '-decision' = %s)
                ORDER BY intake_id
                """,
                (tenant.tenant_id, decision_id, decision_id),
            ).fetchall()
            run_rows = connection.execute(
                """
                SELECT research_run_id, run_json FROM research_runs
                WHERE tenant_id = %s AND decision_file_id = %s
                ORDER BY research_run_id
                """,
                (tenant.tenant_id, decision_id),
            ).fetchall()
            run_ids = [row["research_run_id"] for row in run_rows]
            sources: list[dict[str, Any]] = []
            evidence: list[dict[str, Any]] = []
            research_events: list[dict[str, Any]] = []
            if run_ids:
                sources = [
                    dict(row["source_json"])
                    for row in connection.execute(
                        """
                        SELECT source_json FROM research_source_candidates
                        WHERE tenant_id = %s AND research_run_id = ANY(%s)
                        ORDER BY research_run_id, source_id
                        """,
                        (tenant.tenant_id, run_ids),
                    ).fetchall()
                ]
                evidence = [
                    dict(row["evidence_json"])
                    for row in connection.execute(
                        """
                        SELECT evidence_json FROM research_evidence_candidates
                        WHERE tenant_id = %s AND research_run_id = ANY(%s)
                        ORDER BY research_run_id, evidence_id
                        """,
                        (tenant.tenant_id, run_ids),
                    ).fetchall()
                ]
                research_events = [
                    dict(row["event_json"])
                    for row in connection.execute(
                        """
                        SELECT event_json FROM research_audit_events
                        WHERE tenant_id = %s AND research_run_id = ANY(%s)
                        ORDER BY research_run_id, sequence
                        """,
                        (tenant.tenant_id, run_ids),
                    ).fetchall()
                ]
            intake_ids = [str(row["record_json"]["intake_id"]) for row in intake_records]
            intake_events: list[dict[str, Any]] = []
            if intake_ids:
                intake_events = [
                    dict(row["event_json"])
                    for row in connection.execute(
                        """
                        SELECT event_json FROM intake_audit_events
                        WHERE tenant_id = %s AND intake_id = ANY(%s)
                        ORDER BY intake_id, sequence
                        """,
                        (tenant.tenant_id, intake_ids),
                    ).fetchall()
                ]
            decision_events = [
                dict(row["event_json"])
                for row in connection.execute(
                    """
                    SELECT event_json FROM audit_events
                    WHERE tenant_id = %s AND decision_id = %s ORDER BY sequence
                    """,
                    (tenant.tenant_id, decision_id),
                ).fetchall()
            ]
            lifecycle_events = [
                {
                    **dict(row["event_json"]),
                    "event_hash": row["event_hash"],
                }
                for row in connection.execute(
                    """
                    SELECT event_json, event_hash FROM lifecycle_audit_events
                    WHERE tenant_id = %s AND request_id IN
                        (SELECT request_id FROM deletion_requests
                         WHERE tenant_id = %s AND decision_id = %s)
                    ORDER BY sequence
                    """,
                    (tenant.tenant_id, tenant.tenant_id, decision_id),
                ).fetchall()
            ]
            return {
                "decision/decision-file.json": dict(decision["document_json"]),
                "decision/assurance-report.json": (
                    {} if report is None else dict(report["report_json"])
                ),
                "intake/intake-records.json": [dict(row["record_json"]) for row in intake_records],
                "research/research-runs.json": [dict(row["run_json"]) for row in run_rows],
                "research/sources.json": sources,
                "research/evidence.json": evidence,
                "audit/decision-events.json": decision_events,
                "audit/intake-events.json": intake_events,
                "audit/research-events.json": research_events,
                "audit/lifecycle-events.json": lifecycle_events,
            }
