from __future__ import annotations

import copy
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, cast

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from ..audit import payload_hash
from ..authorization import Permission, authorize
from ..decision_file import validate_semantics
from ..identity import Identity
from ..persistence.postgresql import PostgresConnectionProvider
from ..tenancy import TenantContext
from ..validation import ContractValidator
from .contracts import ImportEnvelope
from .mapping import preview_document


class StrategyStore(Protocol):
    def preview(self, identity: Identity, envelope: ImportEnvelope) -> dict[str, Any]: ...
    def import_artifact(
        self, identity: Identity, envelope: ImportEnvelope, correlation_id: str
    ) -> dict[str, Any]: ...
    def get(self, identity: Identity, artifact_id: str) -> dict[str, Any] | None: ...


class _Session:
    def __init__(self, connection: Any, postgres: bool):
        self.connection = connection
        self.postgres = postgres

    def execute(self, query: str, parameters: tuple[Any, ...] = ()) -> Any:
        return self.connection.execute(
            query.replace("?", "%s") if self.postgres else query, parameters
        )

    def encode(self, value: dict[str, Any]) -> Any:
        return (
            Jsonb(value)
            if self.postgres
            else json.dumps(
                value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            )
        )

    def decode(self, value: Any) -> dict[str, Any]:
        return dict(value) if self.postgres else dict(json.loads(value))


class _StrategyStore:
    @contextmanager
    def session(self, tenant: TenantContext, write: bool) -> Iterator[_Session]:
        raise NotImplementedError
        yield  # pragma: no cover

    @staticmethod
    def _context(identity: Identity, envelope: ImportEnvelope, permission: Permission) -> None:
        authorize(identity, permission)
        if identity.tenant.tenant_id != envelope.tenant_id:
            raise PermissionError("STRATEGY_TENANT_MISMATCH")

    def _document(
        self, session: _Session, identity: Identity, envelope: ImportEnvelope, lock: bool
    ) -> dict[str, Any]:
        query = "SELECT document_json FROM decisions WHERE tenant_id=? AND decision_id=?"
        if lock and session.postgres:
            query = (
                "SELECT document_json FROM decisions WHERE tenant_id=? AND decision_id=? FOR UPDATE"
            )
        row = session.execute(
            query,
            (identity.tenant.tenant_id, envelope.decision_id),
        ).fetchone()
        if row is None:
            raise ValueError("STRATEGY_DECISION_NOT_FOUND")
        return session.decode(row["document_json"])

    def preview(self, identity: Identity, envelope: ImportEnvelope) -> dict[str, Any]:
        envelope = ImportEnvelope.model_validate(envelope.model_dump())
        self._context(identity, envelope, Permission.DECISION_READ)
        with self.session(identity.tenant, False) as session:
            document = self._document(session, identity, envelope, False)
            result = preview_document(identity, envelope, document)
            self._baseline(session, identity, envelope, document, persist=False)
            return result

    def get(self, identity: Identity, artifact_id: str) -> dict[str, Any] | None:
        authorize(identity, Permission.DECISION_READ)
        with self.session(identity.tenant, False) as session:
            return self._get(session, identity.tenant, artifact_id)

    def _get(
        self, session: _Session, tenant: TenantContext, artifact_id: str
    ) -> dict[str, Any] | None:
        row = session.execute(
            "SELECT record_json FROM strategy_records WHERE tenant_id=? AND artifact_id=?",
            (tenant.tenant_id, artifact_id),
        ).fetchone()
        return session.decode(row["record_json"]) if row is not None else None

    def import_artifact(
        self, identity: Identity, envelope: ImportEnvelope, correlation_id: str
    ) -> dict[str, Any]:
        try:
            return self._import_artifact(identity, envelope, correlation_id)
        except UniqueViolation as error:
            if error.diag.constraint_name == "strategy_records_pkey":
                raise ValueError("STRATEGY_ARTIFACT_ID_REUSED") from error
            raise
        except sqlite3.IntegrityError as error:
            if str(error).startswith("UNIQUE constraint failed: strategy_records."):
                raise ValueError("STRATEGY_ARTIFACT_ID_REUSED") from error
            raise

    def _import_artifact(
        self, identity: Identity, envelope: ImportEnvelope, correlation_id: str
    ) -> dict[str, Any]:
        self._context(identity, envelope, Permission.DECISION_CREATE)
        if not correlation_id.strip() or len(correlation_id) > 128:
            raise ValueError("STRATEGY_CORRELATION_REQUIRED")
        # Revalidate model objects to reject assignment/model-copy bypasses.
        envelope = ImportEnvelope.model_validate(envelope.model_dump())
        digest = payload_hash(envelope.model_dump())
        with self.session(identity.tenant, True) as session:
            document = self._document(session, identity, envelope, True)
            replay = self._get(session, identity.tenant, envelope.artifact.get("id", ""))
            if replay is not None:
                if (
                    replay["request_hash"] != digest
                    or replay["decision_id"] != envelope.decision_id
                    or replay["actor_id"] != identity.actor_id
                    or replay.get("actor_kind") != identity.kind.value
                    or replay.get("client_id") != identity.client_id
                ):
                    raise ValueError("STRATEGY_ARTIFACT_ID_REUSED")
                return cast(dict[str, Any], replay["receipt"])
            preview = preview_document(identity, envelope, document)
            now = datetime.now(timezone.utc).isoformat()
            binding = {
                "decision_id": envelope.decision_id,
                "document_hash": payload_hash(document),
                "status": document["status"],
                "bound_at": now,
                "expectation_authority": "draft_expectation"
                if document["status"] == "DRAFT"
                else "case_attachment_unverified",
            }
            if envelope.mode != "baseline":
                self._baseline(session, identity, envelope, document, persist=True, binding=binding)
            else:
                self._correction(session, identity, envelope, binding)
            event = self._event(session, identity, envelope, digest, correlation_id, now)
            updated = preview["document"]
            if envelope.mode == "draft":
                case_event = copy.deepcopy(event)
                previous = document["audit_events"][-1] if document["audit_events"] else None
                case_event["previous_event_hash"] = payload_hash(previous) if previous else None
                updated["audit_events"].append(case_event)
                updated["updated_at"] = max(
                    (now, document["updated_at"]),
                    key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
                )
                ContractValidator().validate("decision-file", updated)
                validate_semantics(updated)
                cursor = session.execute(
                    "UPDATE decisions SET document_json=?,updated_at=CURRENT_TIMESTAMP WHERE tenant_id=? AND decision_id=?",
                    (session.encode(updated), identity.tenant.tenant_id, envelope.decision_id),
                )
                if cursor.rowcount != 1:
                    raise ValueError("STRATEGY_DOCUMENT_CHANGED")
                session.execute(
                    "DELETE FROM reports WHERE tenant_id=? AND decision_id=?",
                    (identity.tenant.tenant_id, envelope.decision_id),
                )
                session.execute(
                    "INSERT INTO audit_events (tenant_id,decision_id,event_id,event_json) VALUES (?,?,?,?)",
                    (
                        identity.tenant.tenant_id,
                        envelope.decision_id,
                        case_event["event_id"],
                        session.encode(case_event),
                    ),
                )
            receipt = {
                "adapter_version": envelope.adapter_version,
                "artifact_id": envelope.artifact["id"],
                "decision_id": envelope.decision_id,
                "mode": envelope.mode,
                "result_document_hash": payload_hash(updated),
                "binding": binding,
                "new_case_proposal": preview["new_case_proposal"],
                "reason_codes": preview["reason_codes"],
            }
            record = {
                "artifact_id": envelope.artifact["id"],
                "tenant_id": identity.tenant.tenant_id,
                "decision_id": envelope.decision_id,
                "mode": envelope.mode,
                "actor_id": identity.actor_id,
                "actor_kind": identity.kind.value,
                "client_id": identity.client_id,
                "actor_roles": sorted(role.value for role in identity.roles),
                "original": copy.deepcopy(envelope.artifact),
                "original_hash": payload_hash(envelope.artifact),
                "envelope": envelope.model_dump(),
                "mapping": preview["mapping"],
                "test_subject_bindings": preview["test_subject_bindings"],
                "baseline_ref": preview["baseline_ref"],
                "binding": binding,
                "request_hash": digest,
                "receipt": receipt,
                "audit": event,
            }
            self._insert(session, identity.tenant, record)
            session.execute(
                "INSERT INTO strategy_events (tenant_id,decision_id,event_id,event_json) VALUES (?,?,?,?)",
                (
                    identity.tenant.tenant_id,
                    envelope.decision_id,
                    event["event_id"],
                    session.encode(event),
                ),
            )
            return receipt

    def _insert(self, session: _Session, tenant: TenantContext, record: dict[str, Any]) -> None:
        session.execute(
            "INSERT INTO strategy_records (tenant_id,artifact_id,decision_id,mode,request_hash,record_json) VALUES (?,?,?,?,?,?)",
            (
                tenant.tenant_id,
                record["artifact_id"],
                record["decision_id"],
                record["mode"],
                record["request_hash"],
                session.encode(record),
            ),
        )

    def _baseline(
        self,
        session: _Session,
        identity: Identity,
        envelope: ImportEnvelope,
        document: dict[str, Any],
        *,
        persist: bool,
        binding: dict[str, Any] | None = None,
    ) -> None:
        if envelope.mode == "baseline":
            existing = self._get(session, identity.tenant, envelope.artifact["id"])
            if existing is not None:
                if (
                    existing["mode"] != "baseline"
                    or existing["original"] != envelope.artifact
                    or existing["decision_id"] != envelope.decision_id
                ):
                    raise ValueError("STRATEGY_BASELINE_IMMUTABLE")
                return
            self._correction(session, identity, envelope, binding or {})
            return
        baseline = envelope.artifact["baseline"]
        if baseline is None:
            return
        existing = self._get(session, identity.tenant, baseline["id"])
        if existing is not None:
            if (
                existing["mode"] != "baseline"
                or existing["original"] != baseline
                or existing["decision_id"] != envelope.decision_id
            ):
                raise ValueError("STRATEGY_BASELINE_IMMUTABLE")
            return
        if envelope.mode == "observation":
            raise ValueError("STRATEGY_BASELINE_NOT_FIXED")
        baseline_envelope = envelope.model_copy(
            update={"mode": "baseline", "selected_option_id": None, "artifact": baseline}
        )
        baseline_binding = dict(binding or {})
        self._correction(session, identity, baseline_envelope, baseline_binding)
        if persist:
            self._insert(
                session,
                identity.tenant,
                {
                    "artifact_id": baseline["id"],
                    "decision_id": envelope.decision_id,
                    "tenant_id": identity.tenant.tenant_id,
                    "mode": "baseline",
                    "original": copy.deepcopy(baseline),
                    "original_hash": payload_hash(baseline),
                    "binding": baseline_binding,
                    "request_hash": payload_hash(baseline_envelope.model_dump()),
                    "actor_id": identity.actor_id,
                    "actor_kind": identity.kind.value,
                    "client_id": identity.client_id,
                    "receipt": {"artifact_id": baseline["id"], "binding": baseline_binding},
                    "parent_artifact_id": envelope.artifact["id"],
                },
            )

    def _correction(
        self,
        session: _Session,
        identity: Identity,
        envelope: ImportEnvelope,
        binding: dict[str, Any],
    ) -> None:
        baseline = envelope.artifact
        if baseline["previous_id"] is None:
            return
        previous = self._get(session, identity.tenant, baseline["previous_id"])
        if (
            previous is None
            or previous["mode"] != "baseline"
            or previous["decision_id"] != envelope.decision_id
        ):
            raise ValueError("STRATEGY_BASELINE_PREDECESSOR_INVALID")
        original = previous["original"]
        if any(
            baseline[key] != original[key] for key in ("original_analysis", "original_decision")
        ) or datetime.fromisoformat(
            baseline["created_at"].replace("Z", "+00:00")
        ) < datetime.fromisoformat(original["created_at"].replace("Z", "+00:00")):
            raise ValueError("STRATEGY_BASELINE_CORRECTION_INVALID")
        rows = session.execute(
            "SELECT record_json FROM strategy_records WHERE tenant_id=? AND decision_id=? AND mode='baseline'",
            (identity.tenant.tenant_id, envelope.decision_id),
        ).fetchall()
        if any(
            session.decode(row["record_json"])["original"]["previous_id"] == baseline["previous_id"]
            for row in rows
        ):
            raise ValueError("STRATEGY_BASELINE_CORRECTION_BRANCH")
        binding.update(previous["binding"])

    def _event(
        self,
        session: _Session,
        identity: Identity,
        envelope: ImportEnvelope,
        digest: str,
        correlation: str,
        now: str,
    ) -> dict[str, Any]:
        row = session.execute(
            "SELECT event_json FROM strategy_events WHERE tenant_id=? AND decision_id=? ORDER BY sequence DESC LIMIT 1",
            (identity.tenant.tenant_id, envelope.decision_id),
        ).fetchone()
        previous = session.decode(row["event_json"]) if row else None
        document = self._document(session, identity, envelope, False)
        return {
            "event_id": "strategy:" + envelope.artifact["id"],
            "event_type": "strategy." + envelope.mode + "-recorded",
            "occurred_at": now,
            "actor": {"id": identity.actor_id, "role": "GENERATOR", "kind": identity.kind.value},
            "from_status": document["status"],
            "to_status": document["status"],
            "reason_codes": ["STRATEGY_ANALYSIS_UNVERIFIED"],
            "payload_hash": digest,
            "previous_event_hash": payload_hash(previous) if previous else None,
            "tenant_id": identity.tenant.tenant_id,
            "correlation_id": correlation,
            "source_channel": "api",
        }


class SqliteStrategyStore(_StrategyStore):
    def __init__(self, database_path: Path):
        self.database_path = database_path

    def initialize(self) -> None:
        path = Path(__file__).parents[1] / "migrations" / "004_strategy_adapter.sql"
        with self.session(TenantContext("migration"), True) as session:
            session.connection.executescript(path.read_text(encoding="utf-8"))

    @contextmanager
    def session(self, tenant: TenantContext, write: bool) -> Iterator[_Session]:
        del tenant  # SQLite predicates below preserve explicit authenticated tenant scope.
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            else:
                connection.execute("PRAGMA query_only=ON")
                connection.execute("BEGIN")
            yield _Session(connection, False)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()


class PostgresStrategyStore(_StrategyStore):
    def __init__(self, connections: PostgresConnectionProvider):
        self.connections = connections

    @contextmanager
    def session(self, tenant: TenantContext, write: bool) -> Iterator[_Session]:
        if write:
            with self.connections.tenant_connection(tenant) as connection:
                yield _Session(connection, True)
        else:
            with self.connections.tenant_snapshot_connection(tenant) as connection:
                yield _Session(connection, True)
