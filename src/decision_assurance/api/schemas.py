from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: Literal["VALIDATION", "REVIEW", "APPROVED", "BLOCKED"]


class AuditPage(BaseModel):
    items: list[dict[str, Any]]
    limit: int
    offset: int
