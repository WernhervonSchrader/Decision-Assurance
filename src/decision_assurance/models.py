from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Outcome(str, Enum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class Severity(str, Enum):
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"


@dataclass(frozen=True, slots=True)
class Finding:
    finding_id: str
    reason_code: str
    severity: Severity
    subject_ref: str | None = None
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "finding_id": self.finding_id,
            "reason_code": self.reason_code,
            "severity": self.severity.value,
        }
        if self.subject_ref is not None:
            result["subject_ref"] = self.subject_ref
        if self.detail is not None:
            result["detail"] = self.detail
        return result


@dataclass(frozen=True, slots=True)
class AssessmentResult:
    outcome: Outcome
    reason_codes: tuple[str, ...]
    human_review: bool
    findings: tuple[Finding, ...]
    report: dict[str, Any]
    audit_events: tuple[dict[str, Any], ...]

    def benchmark_result(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "reason_codes": list(self.reason_codes),
            "human_review": self.human_review,
        }
