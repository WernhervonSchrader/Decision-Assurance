from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .contracts import (
    CandidateFact,
    DerivedFinding,
    FactType,
    PolicyContext,
    SourceReference,
    VerificationReport,
    VerificationStatus,
)


def to_dict(value: Any) -> dict[str, Any]:
    return asdict(value)


def policy_from_dict(value: dict[str, Any]) -> PolicyContext:
    return PolicyContext(**value)


def verification_from_dict(value: dict[str, Any]) -> VerificationReport:
    candidates = tuple(
        CandidateFact(
            fact_id=item["fact_id"],
            fact_type=FactType(item["fact_type"]),
            raw_value=item["raw_value"],
            normalized_value=item.get("normalized_value"),
            source=SourceReference(**item["source"]),
            method=item["method"],
            method_version=item["method_version"],
            extraction_confidence=item["extraction_confidence"],
            verification_status=VerificationStatus(item["verification_status"]),
            unit=item.get("unit"),
            currency=item.get("currency"),
            conflict_refs=tuple(item.get("conflict_refs", ())),
            confirmation_required=item.get("confirmation_required", True),
        )
        for item in value["candidates"]
    )
    findings = tuple(
        DerivedFinding(
            item["finding_id"],
            item["rule_id"],
            tuple(item["fact_refs"]),
            item.get("policy_ref"),
            item["calculation"],
            item["result_code"],
            item.get("uncertainty"),
        )
        for item in value["findings"]
    )
    return VerificationReport(
        value["schema_version"],
        value["intake_id"],
        candidates,
        findings,
        tuple(value["unresolved_requirement_refs"]),
        value["ready"],
        tuple(value["reason_codes"]),
    )
