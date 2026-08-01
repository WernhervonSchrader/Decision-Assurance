from __future__ import annotations

from typing import Any, Protocol

from ..tenancy import TenantContext


class ExportRepository(Protocol):
    def snapshot(self, tenant: TenantContext, decision_id: str) -> dict[str, Any] | None: ...
