from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, cast

from psycopg.types.json import Jsonb

from ..audit import payload_hash
from ..decision_file import validate_semantics
from ..persistence.postgresql import PostgresConnectionProvider
from ..tenancy import TenantContext
from ..validation import ContractValidator
from .contracts import DecisionEvidence, ResearchRun


class DecisionEvidenceHandoffRejected(ValueError):
    pass


class ResearchEvidenceCompiler:
    """Compile eligible research candidates into conservative Decision evidence."""

    def compile(self, run: ResearchRun) -> tuple[DecisionEvidence, ...]:
        compiled: list[DecisionEvidence] = []
        for candidate in run.evidence:
            if not candidate.assessment.usable_for_decision:
                continue
            if candidate.risk.prompt_injection_suspected:
                continue
            status = "UNVERIFIED"
            if candidate.assessment.conflict_status == "CONFLICTING":
                status = "CONFLICTING"
            elif candidate.assessment.freshness_status == "STALE":
                status = "OUTDATED"
            snapshot = next(
                item for item in run.snapshots if item.snapshot_id == candidate.snapshot_id
            )
            compiled.append(
                DecisionEvidence(
                    evidence_id=candidate.evidence_id,
                    research_run_id=run.research_run_id,
                    claim_refs=candidate.claim_refs,
                    source_ref=f"research:{run.research_run_id}:{candidate.evidence_id}",
                    status=status,
                    observed_at=snapshot.retrieved_at,
                    content_hash=candidate.content_hash,
                )
            )
        return tuple(compiled)


class SqliteDecisionEvidenceHandoff:
    """Decision-owned adapter for idempotent, DRAFT-only evidence attachment."""

    def __init__(self, database_path: Path):
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def attach(
        self,
        tenant: TenantContext,
        decision_file_id: str,
        expected_document_hash: str,
        evidence: tuple[DecisionEvidence, ...],
    ) -> dict[str, object]:
        if not evidence:
            raise DecisionEvidenceHandoffRejected("NO_USABLE_EVIDENCE")
        run_ids = {item.research_run_id for item in evidence}
        if len(run_ids) != 1:
            raise DecisionEvidenceHandoffRejected("MIXED_RESEARCH_RUNS")
        run_id = next(iter(run_ids))
        handoff_payload = [
            [item.evidence_id, item.content_hash, item.status]
            for item in sorted(evidence, key=lambda x: x.evidence_id)
        ]
        handoff_id = hashlib.sha256(
            json.dumps(handoff_payload, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT document_json FROM decisions WHERE tenant_id=? AND decision_id=?",
                (tenant.tenant_id, decision_file_id),
            ).fetchone()
            if row is None:
                raise DecisionEvidenceHandoffRejected("DECISION_NOT_FOUND")
            document = cast(dict[str, Any], json.loads(row["document_json"]))
            replay = connection.execute(
                "SELECT 1 FROM research_handoffs WHERE tenant_id=? AND research_run_id=? "
                "AND decision_file_id=? AND handoff_id=?",
                (tenant.tenant_id, run_id, decision_file_id, handoff_id),
            ).fetchone()
            if replay:
                return cast(dict[str, object], document)
            if payload_hash(document) != expected_document_hash:
                raise DecisionEvidenceHandoffRejected("DECISION_DOCUMENT_CHANGED")
            if document["status"] != "DRAFT":
                raise DecisionEvidenceHandoffRejected("DECISION_NOT_DRAFT")
            claim_ids = {item["id"] for item in document["claims"]}
            if any(not set(item.claim_refs).issubset(claim_ids) for item in evidence):
                raise DecisionEvidenceHandoffRejected("CLAIM_REFERENCE_NOT_FOUND")
            existing_ids = {item["id"] for item in document["evidence"]}
            for item in evidence:
                if item.evidence_id not in existing_ids:
                    document["evidence"].append(
                        {
                            "id": item.evidence_id,
                            "claim_refs": list(item.claim_refs),
                            "source_ref": item.source_ref,
                            "status": item.status,
                            "observed_at": item.observed_at,
                            "content_hash": item.content_hash,
                        }
                    )
            document["updated_at"] = max(item.observed_at for item in evidence)
            previous = document["audit_events"][-1] if document["audit_events"] else None
            event = {
                "event_id": f"{decision_file_id}:research-handoff:{handoff_id}",
                "event_type": "research.evidence-attached",
                "occurred_at": document["updated_at"],
                "actor": {"id": "system:research-compiler", "role": "GENERATOR", "kind": "SERVICE"},
                "from_status": "DRAFT",
                "to_status": "DRAFT",
                "reason_codes": ["EXTERNAL_EVIDENCE_ATTACHED_UNVERIFIED"],
                "payload_hash": payload_hash(handoff_payload),
                "previous_event_hash": payload_hash(previous) if previous else None,
                "tenant_id": tenant.tenant_id,
                "source_channel": "api",
            }
            document["audit_events"].append(event)
            ContractValidator().validate("decision-file", document)
            validate_semantics(document)
            serialized = json.dumps(
                document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
            cursor = connection.execute(
                "UPDATE decisions SET document_json=?,updated_at=CURRENT_TIMESTAMP "
                "WHERE tenant_id=? AND decision_id=? AND document_json=?",
                (serialized, tenant.tenant_id, decision_file_id, row["document_json"]),
            )
            if cursor.rowcount != 1:
                raise DecisionEvidenceHandoffRejected("DECISION_DOCUMENT_CHANGED")
            connection.execute(
                "INSERT INTO audit_events (tenant_id,decision_id,event_id,event_json) VALUES (?,?,?,?)",
                (
                    tenant.tenant_id,
                    decision_file_id,
                    event["event_id"],
                    json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                ),
            )
            connection.execute(
                "INSERT INTO research_handoffs "
                "(tenant_id,research_run_id,decision_file_id,handoff_id,result_document_hash) "
                "VALUES (?,?,?,?,?)",
                (
                    tenant.tenant_id,
                    run_id,
                    decision_file_id,
                    handoff_id,
                    payload_hash(document),
                ),
            )
        return cast(dict[str, object], document)


class PostgresDecisionEvidenceHandoff:
    """PostgreSQL handoff with row locking, RLS and replay convergence."""

    def __init__(self, connections: PostgresConnectionProvider):
        self._connections = connections

    def attach(
        self,
        tenant: TenantContext,
        decision_file_id: str,
        expected_document_hash: str,
        evidence: tuple[DecisionEvidence, ...],
    ) -> dict[str, object]:
        if not evidence:
            raise DecisionEvidenceHandoffRejected("NO_USABLE_EVIDENCE")
        run_ids = {item.research_run_id for item in evidence}
        if len(run_ids) != 1:
            raise DecisionEvidenceHandoffRejected("MIXED_RESEARCH_RUNS")
        run_id = next(iter(run_ids))
        handoff_payload = [
            [item.evidence_id, item.content_hash, item.status]
            for item in sorted(evidence, key=lambda item: item.evidence_id)
        ]
        handoff_id = hashlib.sha256(
            json.dumps(handoff_payload, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
        with self._connections.tenant_connection(tenant) as connection:
            row = connection.execute(
                """
                SELECT document_json FROM decisions
                WHERE tenant_id = %s AND decision_id = %s
                FOR UPDATE
                """,
                (tenant.tenant_id, decision_file_id),
            ).fetchone()
            if row is None:
                raise DecisionEvidenceHandoffRejected("DECISION_NOT_FOUND")
            document = cast(dict[str, Any], dict(row["document_json"]))
            replay = connection.execute(
                """
                SELECT 1 FROM research_handoffs
                WHERE tenant_id = %s AND research_run_id = %s
                  AND decision_file_id = %s AND handoff_id = %s
                """,
                (tenant.tenant_id, run_id, decision_file_id, handoff_id),
            ).fetchone()
            if replay is not None:
                return cast(dict[str, object], document)
            if payload_hash(document) != expected_document_hash:
                raise DecisionEvidenceHandoffRejected("DECISION_DOCUMENT_CHANGED")
            if document["status"] != "DRAFT":
                raise DecisionEvidenceHandoffRejected("DECISION_NOT_DRAFT")
            claim_ids = {item["id"] for item in document["claims"]}
            if any(not set(item.claim_refs).issubset(claim_ids) for item in evidence):
                raise DecisionEvidenceHandoffRejected("CLAIM_REFERENCE_NOT_FOUND")
            existing_ids = {item["id"] for item in document["evidence"]}
            for item in evidence:
                if item.evidence_id not in existing_ids:
                    document["evidence"].append(
                        {
                            "id": item.evidence_id,
                            "claim_refs": list(item.claim_refs),
                            "source_ref": item.source_ref,
                            "status": item.status,
                            "observed_at": item.observed_at,
                            "content_hash": item.content_hash,
                        }
                    )
            document["updated_at"] = max(item.observed_at for item in evidence)
            previous = document["audit_events"][-1] if document["audit_events"] else None
            event = {
                "event_id": f"{decision_file_id}:research-handoff:{handoff_id}",
                "event_type": "research.evidence-attached",
                "occurred_at": document["updated_at"],
                "actor": {
                    "id": "system:research-compiler",
                    "role": "GENERATOR",
                    "kind": "SERVICE",
                },
                "from_status": "DRAFT",
                "to_status": "DRAFT",
                "reason_codes": ["EXTERNAL_EVIDENCE_ATTACHED_UNVERIFIED"],
                "payload_hash": payload_hash(handoff_payload),
                "previous_event_hash": payload_hash(previous) if previous else None,
                "tenant_id": tenant.tenant_id,
                "source_channel": "api",
            }
            document["audit_events"].append(event)
            ContractValidator().validate("decision-file", document)
            validate_semantics(document)
            connection.execute(
                """
                UPDATE decisions SET document_json = %s, updated_at = CURRENT_TIMESTAMP
                WHERE tenant_id = %s AND decision_id = %s
                """,
                (Jsonb(document), tenant.tenant_id, decision_file_id),
            )
            connection.execute(
                """
                INSERT INTO audit_events (tenant_id, decision_id, event_id, event_json)
                VALUES (%s, %s, %s, %s)
                """,
                (tenant.tenant_id, decision_file_id, event["event_id"], Jsonb(event)),
            )
            connection.execute(
                """
                INSERT INTO research_handoffs (
                    tenant_id, research_run_id, decision_file_id,
                    handoff_id, result_document_hash
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    tenant.tenant_id,
                    run_id,
                    decision_file_id,
                    handoff_id,
                    payload_hash(document),
                ),
            )
        return cast(dict[str, object], document)
