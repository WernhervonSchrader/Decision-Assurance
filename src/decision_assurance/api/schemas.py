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


class IntakeRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["0.3.0"]
    intake_id: str
    raw_input: str
    locale: Literal["de", "en"] = "en"


class IntakeConfirmationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fact_id: str
    action: Literal["CONFIRM", "CORRECT", "REJECT"]
    new_value: str | None = None
    reason: str
