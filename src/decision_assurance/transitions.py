from __future__ import annotations

import copy
from collections.abc import Callable
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .audit import payload_hash
from .decision_file import validate_semantics
from .validation import ContractValidator


class TransitionRejected(ValueError):
    def __init__(self, reason_codes: list[str]):
        self.reason_codes = reason_codes
        super().__init__("Transition rejected: " + ", ".join(reason_codes))


class CaseStatus(str, Enum):
    DRAFT = "DRAFT"
    VALIDATION = "VALIDATION"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"


ALLOWED_TRANSITIONS = {
    (CaseStatus.DRAFT, CaseStatus.VALIDATION): "VALIDATOR",
    (CaseStatus.DRAFT, CaseStatus.BLOCKED): "VALIDATOR",
    (CaseStatus.VALIDATION, CaseStatus.REVIEW): "VALIDATOR",
    (CaseStatus.VALIDATION, CaseStatus.BLOCKED): "VALIDATOR",
    (CaseStatus.REVIEW, CaseStatus.APPROVED): "APPROVER",
    (CaseStatus.REVIEW, CaseStatus.BLOCKED): "APPROVER",
}


class TransitionPolicy:
    def __init__(self, clock: Callable[[], datetime] | None = None):
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def transition(
        self, document: dict[str, Any], target: str, actor: dict[str, str]
    ) -> dict[str, Any]:
        ContractValidator().validate("decision-file", document)
        validate_semantics(document)
        source = CaseStatus(document["status"])
        destination = CaseStatus(target)
        reasons = self._rejection_reasons(document, source, destination, actor)
        if reasons:
            raise TransitionRejected(reasons)

        updated = copy.deepcopy(document)
        occurred_at = self.clock().isoformat()
        event_number = len(updated["audit_events"]) + 1
        previous = updated["audit_events"][-1] if updated["audit_events"] else None
        event = {
            "event_id": f"{document['decision_id']}:transition:{event_number}",
            "event_type": "status.transitioned",
            "occurred_at": occurred_at,
            "actor": actor,
            "from_status": source.value,
            "to_status": destination.value,
            "reason_codes": ["TRANSITION_AUTHORIZED"],
            "payload_hash": payload_hash(
                {"from": source.value, "to": destination.value, "actor": actor}
            ),
            "previous_event_hash": payload_hash(previous) if previous else None,
        }
        updated["status"] = destination.value
        updated["updated_at"] = occurred_at
        updated["current_owner"] = actor
        updated["audit_events"].append(event)
        ContractValidator().validate("decision-file", updated)
        return updated

    @staticmethod
    def _rejection_reasons(
        document: dict[str, Any], source: CaseStatus, target: CaseStatus, actor: dict[str, str]
    ) -> list[str]:
        reasons: list[str] = []
        required_role = ALLOWED_TRANSITIONS.get((source, target))
        if required_role is None:
            return ["TRANSITION_NOT_ALLOWED"]
        if actor.get("role") != required_role:
            reasons.append("ACTOR_ROLE_NOT_AUTHORIZED")
        if target is CaseStatus.VALIDATION and actor.get("id") == document["created_by"]["id"]:
            reasons.append("GENERATOR_VALIDATOR_NOT_SEPARATE")
        if target is CaseStatus.APPROVED:
            if actor.get("kind") != "HUMAN":
                reasons.append("HUMAN_APPROVER_REQUIRED")
            if actor.get("id") == document["created_by"]["id"]:
                reasons.append("SEPARATION_OF_DUTIES_VIOLATION")
            validator_ids = {
                event["actor"]["id"]
                for event in document["audit_events"]
                if event["to_status"] == "VALIDATION"
            }
            if actor.get("id") in validator_ids:
                reasons.append("VALIDATOR_APPROVER_NOT_SEPARATE")
            if document["decision_outcome"] != "PASS":
                reasons.append("PASS_OUTCOME_REQUIRED")
            if any(
                c["severity"] == "MANDATORY" and not c["satisfied"] for c in document["constraints"]
            ):
                reasons.append("MANDATORY_CONSTRAINT_UNSATISFIED")
            if any(
                c["severity"] == "CRITICAL" and not c["resolved"] for c in document["conflicts"]
            ):
                reasons.append("CRITICAL_CONFLICT_UNRESOLVED")
            if any(r["mandatory"] and not r["satisfied"] for r in document["review_requirements"]):
                reasons.append("MANDATORY_REVIEW_MISSING")
            for requirement in (
                item for item in document["review_requirements"] if item["mandatory"]
            ):
                matching = [
                    approval
                    for approval in document["approvals"]
                    if approval["requirement_ref"] == requirement["id"]
                    and approval["decision"] == "APPROVE"
                    and approval["actor"]["kind"] == "HUMAN"
                    and approval["actor"]["role"] == requirement["required_role"]
                ]
                if not matching:
                    reasons.append("MANDATORY_HUMAN_APPROVAL_MISSING")
        if target is CaseStatus.REVIEW and document["decision_outcome"] == "BLOCK":
            reasons.append("BLOCK_OUTCOME_REQUIRES_BLOCKED_STATUS")
        if target is CaseStatus.BLOCKED and document["decision_outcome"] != "BLOCK":
            reasons.append("BLOCK_OUTCOME_REQUIRED")
        return reasons
