from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: Literal["VALIDATION", "REVIEW", "APPROVED", "BLOCKED"]


class AuditPage(BaseModel):
    items: list[dict]
    limit: int
    offset: int

