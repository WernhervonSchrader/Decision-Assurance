from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from ..tenancy import TenantContext


class InMemoryExportRepository:
    def __init__(self, snapshots: Mapping[tuple[str, str], dict[str, object]]):
        self._snapshots = copy.deepcopy(dict(snapshots))

    def snapshot(self, tenant: TenantContext, decision_id: str) -> dict[str, Any] | None:
        value = self._snapshots.get((tenant.tenant_id, decision_id))
        return None if value is None else copy.deepcopy(value)
