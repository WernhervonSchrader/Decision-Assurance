from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from .audit import payload_hash
from .engine import DecisionAssuranceEngine
from .validation import ContractValidator


class DecisionFileSemanticError(ValueError):
    pass


def canonical_action_digest(action: dict[str, Any]) -> str:
    """Return the normative digest for a canonical action without trusting its digest field."""
    payload = {key: value for key, value in action.items() if key != "canonical_digest"}
    return payload_hash(payload)


def bind_canonical_action(action: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of an action carrying its deterministic canonical digest."""
    bound = copy.deepcopy(action)
    bound["canonical_digest"] = canonical_action_digest(bound)
    return bound


def approval_digest(document: dict[str, Any], approval: dict[str, Any]) -> str:
    """Bind an approval to the case, requester, approver, action, nonce, and decision."""
    payload = {
        "decision_id": document["decision_id"],
        "requested_by": document["requested_by"],
        "requirement_ref": approval["requirement_ref"],
        "approver": approval["approver"],
        "decision": approval["decision"],
        "decided_at": approval["decided_at"],
        "action_digest": approval["action_digest"],
        "nonce": approval["nonce"],
    }
    return payload_hash(payload)


def bind_approval(document: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of an approval carrying its deterministic approval digest."""
    bound = copy.deepcopy(approval)
    bound["approval_digest"] = approval_digest(document, bound)
    return bound


def migrate_decision_file_v0_1_to_v0_2(document: dict[str, Any]) -> dict[str, Any]:
    """Migrate an unapproved v0.1 Decision File without inventing approval authority."""
    if document.get("schema_version") != "0.1.0":
        raise DecisionFileSemanticError("migration requires schema_version 0.1.0")
    if document.get("approvals"):
        raise DecisionFileSemanticError("v0.1 approvals require independent re-approval")
    migrated = copy.deepcopy(document)
    migrated["schema_version"] = "0.2.0"
    migrated["requested_by"] = copy.deepcopy(migrated["created_by"])
    migrated["canonical_action"] = None
    ContractValidator().validate("decision-file", migrated)
    validate_semantics(migrated)
    return migrated


def load_decision_file(path: Path) -> dict[str, Any]:
    try:
        document = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read Decision File {path}: {error}") from error
    ContractValidator().validate("decision-file", document)
    validate_semantics(document)
    return document


def validate_semantics(document: dict[str, Any]) -> None:
    errors: list[str] = []
    if datetime.fromisoformat(
        document["updated_at"].replace("Z", "+00:00")
    ) < datetime.fromisoformat(document["created_at"].replace("Z", "+00:00")):
        errors.append("updated_at must not be earlier than created_at")
    claim_ids = [item["id"] for item in document["claims"]]
    if len(claim_ids) != len(set(claim_ids)):
        errors.append("claims contain duplicate ids")
    evidence_ids = [item["id"] for item in document["evidence"]]
    if len(evidence_ids) != len(set(evidence_ids)):
        errors.append("evidence contains duplicate ids")
    unknown_claims = sorted(
        {ref for item in document["evidence"] for ref in item["claim_refs"] if ref not in claim_ids}
    )
    if unknown_claims:
        errors.append("evidence references unknown claims: " + ", ".join(unknown_claims))
    requirements = {item["id"]: item for item in document["review_requirements"]}
    requirement_ids = set(requirements)
    unknown_requirements = sorted(
        {
            item["requirement_ref"]
            for item in document["approvals"]
            if item["requirement_ref"] not in requirement_ids
        }
    )
    if unknown_requirements:
        errors.append(
            "approvals reference unknown requirements: " + ", ".join(unknown_requirements)
        )
    canonical_action = document["canonical_action"]
    if canonical_action is not None:
        if canonical_action["canonical_digest"] != canonical_action_digest(canonical_action):
            errors.append("canonical_action digest does not match canonical content")
        if canonical_action["reversibility_class"] != "READ_ONLY" and not any(
            item["mandatory"] and item["required_role"] == "APPROVER"
            for item in document["review_requirements"]
        ):
            errors.append("non-read-only canonical_action requires a mandatory APPROVER review")
    nonces = [item["nonce"] for item in document["approvals"]]
    if len(nonces) != len(set(nonces)):
        errors.append("approvals contain a reused nonce")
    if document["approvals"] and document["status"] not in {"REVIEW", "APPROVED", "BLOCKED"}:
        errors.append("approvals are not allowed before REVIEW")
    expected_action_digest = (
        canonical_action["canonical_digest"] if canonical_action is not None else None
    )
    for item in document["approvals"]:
        approver = item["approver"]
        requirement = requirements.get(item["requirement_ref"])
        if requirement is not None and approver["role"] != requirement["required_role"]:
            errors.append(
                f"approval {item['requirement_ref']} approver role does not match requirement"
            )
        if approver["kind"] != "HUMAN":
            errors.append(f"approval {item['requirement_ref']} requires a human approver")
        if approver["id"] in {document["created_by"]["id"], document["requested_by"]["id"]}:
            errors.append(f"approval {item['requirement_ref']} violates actor independence")
        if item["action_digest"] != expected_action_digest:
            errors.append(f"approval {item['requirement_ref']} is not bound to canonical_action")
        if item["approval_digest"] != approval_digest(document, item):
            errors.append(f"approval {item['requirement_ref']} digest does not match approval")
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
                claim["id"] in evidence["claim_refs"] and evidence["status"] not in {"UNAVAILABLE"}
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
            "validator": {
                "id": "decision-assurance-engine",
                "role": "VALIDATOR",
                "kind": "SERVICE",
            },
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
        actors["approver"] = approvals[-1]["approver"]["id"]
    return actors
