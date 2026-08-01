from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Protocol

from .production.ports import StructuredLoggerPort

AUTH_REASON_CODES = frozenset(
    {
        "AUTH_TOKEN_MISSING",
        "AUTH_TOKEN_INVALID",
        "AUTH_TOKEN_EXPIRED",
        "AUTH_ISSUER_MISMATCH",
        "AUTH_AUDIENCE_MISMATCH",
        "AUTH_ROLE_REQUIRED",
        "AUTH_TENANT_MISMATCH",
        "AUTH_CROSS_TENANT_DENIED",
        "AUTH_ALLOWED",
    }
)
_SENSITIVE = re.compile(r"(?i)(bearer\s+|password|refresh.?token|client.?secret)")


@dataclass(frozen=True, slots=True)
class SecurityEvent:
    event_id: str
    event_type: str
    schema_version: str
    occurred_at: str
    decision: str
    actor_ref: str
    tenant_id: str | None
    client_id: str | None
    correlation_id: str
    reason_code: str
    permission: str | None = None

    @classmethod
    def create(
        cls,
        *,
        event_type: str,
        decision: str,
        actor_ref: str,
        tenant_id: str | None,
        client_id: str | None,
        correlation_id: str,
        reason_code: str,
        permission: str | None = None,
    ) -> SecurityEvent:
        event = cls(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            schema_version="1.0.0",
            occurred_at=datetime.now(timezone.utc).isoformat(),
            decision=decision,
            actor_ref=actor_ref,
            tenant_id=tenant_id,
            client_id=client_id,
            correlation_id=correlation_id,
            reason_code=reason_code,
            permission=permission,
        )
        event._validate()
        return event

    def _validate(self) -> None:
        if self.decision not in {"ALLOWED", "DENIED"}:
            raise ValueError("INVALID_SECURITY_DECISION")
        if self.reason_code not in AUTH_REASON_CODES:
            raise ValueError("INVALID_AUTH_REASON_CODE")
        values = (
            self.event_id,
            self.event_type,
            self.actor_ref,
            self.tenant_id,
            self.client_id,
            self.correlation_id,
            self.permission,
        )
        if any(value is not None and (not value.strip() or len(value) > 256) for value in values):
            raise ValueError("INVALID_SECURITY_EVENT")
        if any(value is not None and _SENSITIVE.search(value) for value in values):
            raise ValueError("SENSITIVE_SECURITY_EVENT_VALUE")

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


class SecurityEventSink(Protocol):
    def record(self, event: SecurityEvent) -> None: ...


class NullSecurityEventSink:
    def record(self, event: SecurityEvent) -> None:
        del event


class InMemorySecurityEventSink:
    def __init__(self) -> None:
        self.events: list[SecurityEvent] = []

    def record(self, event: SecurityEvent) -> None:
        self.events.append(event)


class LoggingSecurityEventSink:
    def __init__(self, logger: StructuredLoggerPort):
        self._logger = logger

    def record(self, event: SecurityEvent) -> None:
        self._logger.emit(
            "security.audit",
            level="INFO" if event.decision == "ALLOWED" else "WARNING",
            correlation_id=event.correlation_id,
            fields={
                "schema_version": event.schema_version,
                "event_id": event.event_id,
                "security_event_type": event.event_type,
                "decision": event.decision,
                "actor_ref": event.actor_ref,
                "tenant_id": event.tenant_id,
                "client_id": event.client_id,
                "reason_code": event.reason_code,
                "permission": event.permission,
            },
        )
