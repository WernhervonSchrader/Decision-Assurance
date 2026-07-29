from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntakeStatus(str, Enum):
    RECEIVED = "RECEIVED"
    EXTRACTED = "EXTRACTED"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    READY = "READY"
    COMPILED = "COMPILED"
    REJECTED = "REJECTED"


class VerificationStatus(str, Enum):
    UNRESOLVED = "UNRESOLVED"
    VERIFIED = "VERIFIED"
    HUMAN_CONFIRMED = "HUMAN_CONFIRMED"
    REJECTED = "REJECTED"


class FactType(str, Enum):
    AMOUNT = "AMOUNT"
    DISCOUNT_PERCENT = "DISCOUNT_PERCENT"
    DISCOUNT_LIMIT_PERCENT = "DISCOUNT_LIMIT_PERCENT"
    MARGIN_PERCENT = "MARGIN_PERCENT"
    MIN_MARGIN_PERCENT = "MIN_MARGIN_PERCENT"
    PAYMENT_TERM_DAYS = "PAYMENT_TERM_DAYS"
    DURATION_MONTHS = "DURATION_MONTHS"
    DATE = "DATE"
    EVIDENCE_DATE = "EVIDENCE_DATE"
    POLICY_CLAIM = "POLICY_CLAIM"
    EXCEPTION_CLAIM = "EXCEPTION_CLAIM"
    APPROVAL_CLAIM = "APPROVAL_CLAIM"
    ROLE_CLAIM = "ROLE_CLAIM"
    UNTRUSTED_INSTRUCTION = "UNTRUSTED_INSTRUCTION"


@dataclass(frozen=True, slots=True)
class IntakeRequest:
    schema_version: str
    intake_id: str
    raw_input: str
    locale: str = "en"
    content_language: str | None = None


@dataclass(frozen=True, slots=True)
class SourceReference:
    source_id: str
    start: int
    end: int
    content_hash: str


@dataclass(frozen=True, slots=True)
class CandidateFact:
    fact_id: str
    fact_type: FactType
    raw_value: str
    normalized_value: str | None
    source: SourceReference
    method: str
    method_version: str
    extraction_confidence: float
    verification_status: VerificationStatus = VerificationStatus.UNRESOLVED
    unit: str | None = None
    currency: str | None = None
    conflict_refs: tuple[str, ...] = ()
    confirmation_required: bool = True


@dataclass(frozen=True, slots=True)
class IntakeConflict:
    conflict_id: str
    fact_type: FactType
    fact_refs: tuple[str, ...]
    reason_code: str = "CONFLICTING_CANDIDATES"


@dataclass(frozen=True, slots=True)
class VerificationRequirement:
    requirement_id: str
    fact_type: FactType
    reason_code: str
    mandatory: bool = True


@dataclass(frozen=True, slots=True)
class ExtractionReport:
    schema_version: str
    intake_id: str
    method: str
    method_version: str
    locale: str
    candidates: tuple[CandidateFact, ...]
    conflicts: tuple[IntakeConflict, ...]
    requirements: tuple[VerificationRequirement, ...]


@dataclass(frozen=True, slots=True)
class DerivedFinding:
    finding_id: str
    rule_id: str
    fact_refs: tuple[str, ...]
    policy_ref: str | None
    calculation: str
    result_code: str
    uncertainty: str | None = None


@dataclass(frozen=True, slots=True)
class HumanConfirmation:
    confirmation_id: str
    fact_id: str
    action: str
    actor_id: str
    old_value: str | None
    new_value: str | None
    reason: str
    occurred_at: str


@dataclass(frozen=True, slots=True)
class IntakeAuditEvent:
    event_id: str
    event_type: str
    occurred_at: str
    actor_id: str
    from_status: IntakeStatus
    to_status: IntakeStatus
    reason_codes: tuple[str, ...]
    payload_hash: str
    previous_event_hash: str | None


@dataclass(slots=True)
class IntakeRecord:
    schema_version: str
    intake_id: str
    status: IntakeStatus
    raw_input: str
    locale: str
    created_at: str
    updated_at: str
    raw_input_hash: str
    extraction: ExtractionReport | None = None
    confirmations: list[HumanConfirmation] = field(default_factory=list)
    findings: list[DerivedFinding] = field(default_factory=list)
    audit_events: list[IntakeAuditEvent] = field(default_factory=list)
    compiled_decision_id: str | None = None


@dataclass(frozen=True, slots=True)
class CompilationReport:
    schema_version: str
    intake_id: str
    ready: bool
    decision_id: str | None
    used_fact_refs: tuple[str, ...]
    unresolved_requirement_refs: tuple[str, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PolicyContext:
    policy_id: str
    policy_version: str
    effective_date: str
    maximum_discount_percent: str
    minimum_margin_percent: str
    maximum_duration_months_without_exception: int
    requires_approval_above_amount: str
    maximum_evidence_age_days: int = 365


@dataclass(frozen=True, slots=True)
class VerificationReport:
    schema_version: str
    intake_id: str
    candidates: tuple[CandidateFact, ...]
    findings: tuple[DerivedFinding, ...]
    unresolved_requirement_refs: tuple[str, ...]
    ready: bool
    reason_codes: tuple[str, ...]


def enum_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value
