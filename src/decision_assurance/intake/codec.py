from __future__ import annotations

import json
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
    result = json.loads(json.dumps(asdict(value), ensure_ascii=False))
    _remove_empty_confirmation_identity(result)
    return result  # type: ignore[no-any-return]


def _remove_empty_confirmation_identity(value: Any) -> None:
    if isinstance(value, dict):
        for key in ("confirmed_by_actor_id", "confirmed_by_role"):
            if value.get(key) is None:
                value.pop(key, None)
        for item in value.values():
            _remove_empty_confirmation_identity(item)
    elif isinstance(value, list):
        for item in value:
            _remove_empty_confirmation_identity(item)


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
            confirmed_by_actor_id=item.get("confirmed_by_actor_id"),
            confirmed_by_role=item.get("confirmed_by_role"),
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
