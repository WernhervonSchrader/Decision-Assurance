from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime


class EventVersionError(ValueError):
    pass


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise EventVersionError(code)
    return value


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    event_type: str
    schema_version: str
    event_id: str
    occurred_at: datetime
    tenant_id: str
    actor_id: str
    correlation_id: str
    source_component: str
    payload: Mapping[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "timestamp": self.occurred_at.isoformat().replace("+00:00", "Z"),
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "correlation_id": self.correlation_id,
            "source_component": self.source_component,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True, slots=True)
class MigrationResult:
    event: EventEnvelope
    source_version: str
    target_version: str
    original_hash: str


class EventRegistry:
    _CURRENT = "1.0.0"
    _LEGACY = "0.9.0"
    _SUPPORTED_TYPES = frozenset(
        {
            "deployment.evidence-created",
            "deployment.pilot-accepted",
            "export.signed",
            "export.verification-failed",
            "recovery.test-completed",
            "session.revoked",
        }
    )

    def parse(self, value: Mapping[str, object]) -> EventEnvelope:
        if value.get("schema_version") != self._CURRENT:
            raise EventVersionError("EVENT_VERSION_UNSUPPORTED")
        required = {
            "event_type",
            "schema_version",
            "event_id",
            "timestamp",
            "tenant_id",
            "actor_id",
            "correlation_id",
            "source_component",
            "payload",
        }
        if set(value) != required or not isinstance(value.get("payload"), dict):
            raise EventVersionError("EVENT_ENVELOPE_INVALID")
        payload = value["payload"]
        if not isinstance(payload, dict):
            raise EventVersionError("EVENT_ENVELOPE_INVALID")
        try:
            occurred = datetime.fromisoformat(
                _text(value["timestamp"], "EVENT_TIMESTAMP_INVALID").replace("Z", "+00:00")
            )
        except ValueError:
            raise EventVersionError("EVENT_TIMESTAMP_INVALID") from None
        if occurred.tzinfo is None:
            raise EventVersionError("EVENT_TIMESTAMP_INVALID")
        event_type = _text(value["event_type"], "EVENT_TYPE_INVALID")
        if event_type not in self._SUPPORTED_TYPES:
            raise EventVersionError("EVENT_TYPE_UNSUPPORTED")
        return EventEnvelope(
            event_type,
            self._CURRENT,
            _text(value["event_id"], "EVENT_ID_INVALID"),
            occurred,
            _text(value["tenant_id"], "EVENT_TENANT_INVALID"),
            _text(value["actor_id"], "EVENT_ACTOR_INVALID"),
            _text(value["correlation_id"], "EVENT_CORRELATION_INVALID"),
            _text(value["source_component"], "EVENT_SOURCE_INVALID"),
            dict(payload),
        )

    def migrate(self, value: Mapping[str, object], *, target_version: str) -> MigrationResult:
        if value.get("schema_version") != self._LEGACY or target_version != self._CURRENT:
            raise EventVersionError("EVENT_MIGRATION_UNSUPPORTED")
        legacy_required = {
            "event_type",
            "schema_version",
            "event_id",
            "timestamp",
            "tenant_id",
            "actor_id",
            "correlation_id",
            "source",
            "payload",
        }
        if set(value) != legacy_required:
            raise EventVersionError("EVENT_MIGRATION_DATA_LOSS")
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
        migrated = dict(value)
        migrated["schema_version"] = target_version
        migrated["source_component"] = migrated.pop("source")
        return MigrationResult(
            self.parse(migrated),
            self._LEGACY,
            self._CURRENT,
            "sha256:" + hashlib.sha256(canonical).hexdigest(),
        )
