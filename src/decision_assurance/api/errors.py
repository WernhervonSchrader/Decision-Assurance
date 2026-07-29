from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ApiError(Exception):
    status_code: int
    code: str
    details: dict[str, Any] | None = None
