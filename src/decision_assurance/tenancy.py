from __future__ import annotations

import re
from dataclasses import dataclass

_TENANT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: str

    def __post_init__(self) -> None:
        if not _TENANT_ID.fullmatch(self.tenant_id):
            raise ValueError("INVALID_TENANT_ID")
