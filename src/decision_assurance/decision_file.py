from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .engine import DecisionAssuranceEngine
from .audit import payload_hash
from .validation import ContractValidator


class DecisionFileSemanticError(ValueError):
    pass


def load_decision_file(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read Decision File {path}: {error}") from error
    ContractValidator().validate("decision-file", document)
    validate_semantics(document)
    return document


def validate_semantics(document: dict[str, Any]) -> None:
    errors: list[str] = []
    if datetime.fromisoformat(document["updated_at"].replace("Z", "+00:00")) < datetime.fromisoformat(document["created_at"].replace("Z", "+00:00")):
        errors.append("updated_at must not be earlier than created_at")
    claim_ids = [item["id"] for item in document["claims"]]
    if len(claim_ids) != len(set(claim_ids)):
        errors.append("claims contain duplicate ids")
    evidence_ids = [item["id"] for item in document["evidence"]]
    if len(evidence_ids) != len(set(evidence_ids)):
        errors.append("evidence contains duplicate ids")
    unknown_claims = sorted({ref for item in document["evidence"] for ref in item["claim_refs"] if ref not in claim_ids})
    if unknown_claims:
        errors.append("evidence references unknown claims: " + ", ".join(unknown_claims))
    requirement_ids = {item["id"] for item in document["review_requirements"]}
    unknown_requirements = sorted({item["requirement_ref"] for item in document["approvals"] if item["requirement_ref"] not in requirement_ids})
    if unknown_requirements:
        errors.append("approvals reference unknown requirements: " + ", ".join(unknown_requirements))
    if errors:
        raise DecisionFileSemanticError("; ".join(errors))


def evaluate_decision_file(
    document: dict[str, Any], *, engine: DecisionAssuranceEngine | None = None
) -> tuple[dict[str, Any], Any]:
    ContractValidator().validate("decision-file", document)
    validate_semantics(document)
    request = {
        "decision_id": document["decision_id"],
        "evidence": [
            {
                "id": item["id"],
                "status": item["status"],
                "fabricated": item["status"] == "FABRICATED",
            }
            for item in document["evidence"]
        ],
        "mandatory_evidence_missing": any(
            claim["mandatory_evidence"]
            and not any(
                claim["id"] in evidence["claim_refs"]
                and evidence["status"] not in {"UNAVAILABLE"}
                for evidence in document["evidence"]
            )
            for claim in document["claims"]
        ),
        "constraints": document["constraints"],
        "policies": document["policies"],
        "conflicts": document["conflicts"],
        "actors": _actors(document),
        "risk": {
            "high_impact": any(risk["level"] in {"HIGH", "CRITICAL"} for risk in document["risks"]),
            "unresolved_uncertainty": any(risk["unresolved"] for risk in document["risks"]),
        },
        "policy_version": ",".join(policy["version"] for policy in document["policies"]) or "none",
    }
    result = (engine or DecisionAssuranceEngine()).assess(request)
    updated = copy.deepcopy(document)
    updated["decision_outcome"] = result.outcome.value
    updated["outcome_reasons"] = list(result.reason_codes)
    occurred_at = result.report["created_at"]
    updated["updated_at"] = occurred_at
    updated["validation_results"].append(
        {
            "validator": {"id": "decision-assurance-engine", "role": "VALIDATOR", "kind": "SERVICE"},
            "result": result.outcome.value,
            "reason_codes": list(result.reason_codes),
            "validated_at": occurred_at,
        }
    )
    previous = updated["audit_events"][-1] if updated["audit_events"] else None
    updated["audit_events"].append(
        {
            "event_id": f"{document['decision_id']}:evaluation:{len(updated['audit_events']) + 1}",
            "event_type": "decision.evaluated",
            "occurred_at": occurred_at,
            "actor": {"id": "decision-assurance-engine", "role": "VALIDATOR", "kind": "SERVICE"},
            "from_status": document["status"],
            "to_status": document["status"],
            "reason_codes": list(result.reason_codes),
            "payload_hash": payload_hash(result.report),
            "previous_event_hash": payload_hash(previous) if previous else None,
        }
    )
    ContractValidator().validate("decision-file", updated)
    return updated, result


def _actors(document: dict[str, Any]) -> dict[str, str]:
    actors: dict[str, str] = {"generator": document["created_by"]["id"]}
    approvals = document["approvals"]
    if approvals:
        actors["approver"] = approvals[-1]["actor"]["id"]
    return actors
