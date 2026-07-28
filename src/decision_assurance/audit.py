from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable


def payload_hash(payload: Any) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


@dataclass(slots=True)
class AuditLedger:
    decision_id: str
    now: Callable[[], datetime]
    actor_ref: str = "decision-assurance-engine"
    correlation_id: str | None = None
    _events: list[dict[str, Any]] = field(default_factory=list)

    def append(self, event_type: str, payload: Any) -> dict[str, Any]:
        previous_hash = payload_hash(self._events[-1]) if self._events else None
        sequence = len(self._events) + 1
        event: dict[str, Any] = {
            "event_id": f"{self.decision_id}:event:{sequence}",
            "decision_id": self.decision_id,
            "event_type": event_type,
            "occurred_at": self.now().isoformat(),
            "actor_ref": self.actor_ref,
            "payload_hash": payload_hash(payload),
            "previous_event_hash": previous_hash,
            "version_refs": ["das:0.1.0", "engine:0.1.0"],
        }
        if self.correlation_id:
            event["correlation_id"] = self.correlation_id
        self._events.append(event)
        return event

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(event) for event in self._events)

