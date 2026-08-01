from __future__ import annotations

from psycopg.types.json import Jsonb

from ..events.registry import EventEnvelope, EventRegistry
from ..persistence.postgresql import PostgresConnectionProvider
from ..tenancy import TenantContext


class PostgresAcceptanceAudit:
    """Tenant-scoped, append-only persistence for pilot acceptance events."""

    def __init__(self, connections: PostgresConnectionProvider):
        self._connections = connections
        self._registry = EventRegistry()

    def append(self, event: EventEnvelope) -> None:
        payload = event.as_dict()
        self._registry.parse(payload)
        with self._connections.tenant_connection(TenantContext(event.tenant_id)) as connection:
            connection.execute(
                """
                INSERT INTO deployment_acceptance_events
                    (tenant_id,event_id,occurred_at,event_json)
                VALUES (%s,%s,%s,%s)
                """,
                (event.tenant_id, event.event_id, event.occurred_at, Jsonb(payload)),
            )
