from __future__ import annotations

import hashlib
import json
from typing import Any

from .codec import to_data
from .contracts import ResearchAuditEvent, ResearchRun, ResearchStatus
from .lifecycle import transition


def _hash(value: Any) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def apply_transition(
    run: ResearchRun,
    target: ResearchStatus,
    *,
    occurred_at: str,
    actor_id: str,
    reason_codes: tuple[str, ...],
    payload: Any,
    retry: bool = False,
) -> ResearchAuditEvent:
    source = run.status
    transition(source, target, retry=retry)
    previous = run.audit_events[-1] if run.audit_events else None
    event = ResearchAuditEvent(
        event_id=f"{run.research_run_id}:research-audit:{len(run.audit_events) + 1}",
        event_type="research.status-transitioned",
        occurred_at=occurred_at,
        tenant_id=run.tenant_id,
        actor_id=actor_id,
        from_status=source,
        to_status=target,
        reason_codes=reason_codes,
        correlation_id=run.correlation_id,
        payload_hash=_hash(payload),
        previous_event_hash=_hash(to_data(previous)) if previous else None,
    )
    run.status = target
    run.updated_at = occurred_at
    run.audit_events.append(event)
    return event
