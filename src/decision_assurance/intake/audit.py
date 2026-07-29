from __future__ import annotations

import hashlib
import json
from typing import Any

from .contracts import IntakeStatus


def intake_audit_event(
    *,
    intake_id: str,
    sequence: int,
    event_type: str,
    occurred_at: str,
    actor_id: str,
    from_status: IntakeStatus,
    to_status: IntakeStatus,
    reason_codes: tuple[str, ...],
    payload: Any,
    previous_event: dict[str, Any] | None,
) -> dict[str, Any]:
    previous_hash = _event_hash(previous_event) if previous_event else None
    return {
        "event_id": f"{intake_id}:intake-audit:{sequence}",
        "event_type": event_type,
        "occurred_at": occurred_at,
        "actor_id": actor_id,
        "from_status": from_status.value,
        "to_status": to_status.value,
        "reason_codes": list(reason_codes),
        "payload_hash": _hash(payload),
        "previous_event_hash": previous_hash,
    }


def _event_hash(event: dict[str, Any]) -> str:
    return _hash(event)


def _hash(value: Any) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(serialized.encode()).hexdigest()
