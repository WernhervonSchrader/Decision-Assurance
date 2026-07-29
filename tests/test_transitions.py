import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from decision_assurance.decision_file import evaluate_decision_file
from decision_assurance.transitions import TransitionPolicy, TransitionRejected

ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
VALIDATOR = {"id": "validator-1", "role": "VALIDATOR", "kind": "HUMAN"}
APPROVER = {"id": "approver-1", "role": "APPROVER", "kind": "HUMAN"}


def fixture() -> dict:
    return json.loads(
        (ROOT / "examples" / "decision-cases" / "low-risk-pass.json").read_text(encoding="utf-8")
    )


def test_full_draft_to_approved_process_is_audited() -> None:
    policy = TransitionPolicy(clock=lambda: NOW)
    document, _ = evaluate_decision_file(fixture())
    document = policy.transition(document, "VALIDATION", VALIDATOR)
    document = policy.transition(document, "REVIEW", VALIDATOR)
    document["review_requirements"][0]["satisfied"] = True
    document["approvals"] = [
        {
            "requirement_ref": "APPROVAL-1",
            "actor": APPROVER,
            "decision": "APPROVE",
            "decided_at": NOW.isoformat(),
        }
    ]
    document = policy.transition(document, "APPROVED", APPROVER)
    assert document["status"] == "APPROVED"
    assert [event["to_status"] for event in document["audit_events"]] == [
        "DRAFT",
        "VALIDATION",
        "REVIEW",
        "APPROVED",
    ]
    assert all(event["previous_event_hash"] for event in document["audit_events"][1:])


def test_draft_cannot_jump_to_approved() -> None:
    with pytest.raises(TransitionRejected, match="TRANSITION_NOT_ALLOWED"):
        TransitionPolicy().transition(fixture(), "APPROVED", APPROVER)


def test_agent_cannot_simulate_human_approval() -> None:
    document, _ = evaluate_decision_file(fixture())
    document["status"] = "REVIEW"
    document["review_requirements"][0]["satisfied"] = True
    with pytest.raises(TransitionRejected) as error:
        TransitionPolicy().transition(
            document, "APPROVED", {"id": "agent-x", "role": "APPROVER", "kind": "AGENT"}
        )
    assert "HUMAN_APPROVER_REQUIRED" in error.value.reason_codes


def test_blocked_is_terminal() -> None:
    document = fixture()
    document["status"] = "BLOCKED"
    document["decision_outcome"] = "BLOCK"
    with pytest.raises(TransitionRejected, match="TRANSITION_NOT_ALLOWED"):
        TransitionPolicy().transition(document, "REVIEW", VALIDATOR)


def test_mandatory_constraint_prevents_approval() -> None:
    document = fixture()
    document["status"] = "REVIEW"
    document["decision_outcome"] = "PASS"
    document["constraints"][0]["satisfied"] = False
    document["review_requirements"][0]["satisfied"] = True
    with pytest.raises(TransitionRejected) as error:
        TransitionPolicy().transition(document, "APPROVED", APPROVER)
    assert "MANDATORY_CONSTRAINT_UNSATISFIED" in error.value.reason_codes
