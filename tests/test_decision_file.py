from pathlib import Path

import pytest

from decision_assurance.decision_file import (
    DecisionFileSemanticError,
    bind_approval,
    bind_canonical_action,
    evaluate_decision_file,
    load_decision_file,
    migrate_decision_file_v0_1_to_v0_2,
    validate_semantics,
)
from decision_assurance.validation import ContractValidationError

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    "path", sorted((ROOT / "examples" / "decision-cases").glob("*.json")), ids=lambda p: p.stem
)
def test_examples_are_valid(path: Path) -> None:
    assert load_decision_file(path)["schema_version"] == "0.2.0"


@pytest.mark.parametrize(
    "path", sorted((ROOT / "tests" / "fixtures" / "invalid").glob("*.json")), ids=lambda p: p.stem
)
def test_invalid_fixtures_are_rejected_with_context(path: Path) -> None:
    with pytest.raises(ContractValidationError) as error:
        load_decision_file(path)
    assert str(error.value)


@pytest.mark.parametrize(
    ("name", "outcome"),
    [
        ("low-risk-pass.json", "PASS"),
        ("missing-evidence-review.json", "REVIEW"),
        ("hard-constraint-block.json", "BLOCK"),
    ],
)
def test_decision_file_evaluation(name: str, outcome: str) -> None:
    document = load_decision_file(ROOT / "examples" / "decision-cases" / name)
    updated, result = evaluate_decision_file(document)
    assert updated["decision_outcome"] == outcome
    assert result.outcome.value == outcome


def test_critical_conflict_blocks() -> None:
    document = load_decision_file(ROOT / "examples" / "decision-cases" / "low-risk-pass.json")
    document["conflicts"] = [{"id": "C-1", "severity": "CRITICAL", "resolved": False}]
    _, result = evaluate_decision_file(document)
    assert result.outcome.value == "BLOCK"
    assert "CRITICAL_CONFLICT_UNRESOLVED" in result.reason_codes


def test_unknown_claim_reference_is_rejected_semantically() -> None:
    document = load_decision_file(ROOT / "examples" / "decision-cases" / "low-risk-pass.json")
    document["evidence"][0]["claim_refs"] = ["UNKNOWN"]
    with pytest.raises(DecisionFileSemanticError, match="unknown claims"):
        validate_semantics(document)


def action_case() -> dict:  # type: ignore[type-arg]
    document = load_decision_file(ROOT / "examples" / "decision-cases" / "low-risk-pass.json")
    document["status"] = "REVIEW"
    document["canonical_action"] = bind_canonical_action(
        {
            "action_id": "ACTION-1",
            "action_type": "quote.publish",
            "effect": "Publish the approved quote to the customer portal.",
            "target": {"type": "sales-quote", "id": "QUOTE-1"},
            "parameters": {"currency": "EUR", "amount": "40000.00"},
            "reversibility_class": "EXTERNALLY_REVERSIBLE",
            "tenant_id": "tenant-a",
            "execution_context_hash": "sha256:" + "a" * 64,
        }
    )
    approval = {
        "requirement_ref": "APPROVAL-1",
        "approver": {"id": "approver-1", "role": "APPROVER", "kind": "HUMAN"},
        "decision": "APPROVE",
        "decided_at": "2026-07-28T07:00:00Z",
        "action_digest": document["canonical_action"]["canonical_digest"],
        "nonce": "single_use_nonce_000000000001",
    }
    document["approvals"] = [bind_approval(document, approval)]
    return document


def test_canonical_action_and_approval_binding_are_valid() -> None:
    validate_semantics(action_case())


def test_action_parameter_tampering_after_approval_is_rejected() -> None:
    document = action_case()
    document["canonical_action"]["parameters"]["amount"] = "90000.00"
    with pytest.raises(DecisionFileSemanticError, match="canonical_action digest"):
        validate_semantics(document)


def test_approval_digest_tampering_is_rejected() -> None:
    document = action_case()
    document["approvals"][0]["decided_at"] = "2026-07-28T08:00:00Z"
    with pytest.raises(DecisionFileSemanticError, match="digest does not match approval"):
        validate_semantics(document)


def test_approval_bound_to_different_action_is_rejected() -> None:
    document = action_case()
    document["approvals"][0]["action_digest"] = "sha256:" + "b" * 64
    document["approvals"][0] = bind_approval(document, document["approvals"][0])
    with pytest.raises(DecisionFileSemanticError, match="not bound to canonical_action"):
        validate_semantics(document)


def test_approval_nonce_replay_is_rejected() -> None:
    document = action_case()
    document["approvals"].append(dict(document["approvals"][0]))
    with pytest.raises(DecisionFileSemanticError, match="reused nonce"):
        validate_semantics(document)


def test_approval_before_review_is_rejected() -> None:
    document = action_case()
    document["status"] = "DRAFT"
    with pytest.raises(DecisionFileSemanticError, match="not allowed before REVIEW"):
        validate_semantics(document)


def test_requester_cannot_approve_own_action() -> None:
    document = action_case()
    document["approvals"][0]["approver"] = {
        "id": document["requested_by"]["id"],
        "role": "APPROVER",
        "kind": "HUMAN",
    }
    document["approvals"][0] = bind_approval(document, document["approvals"][0])
    with pytest.raises(DecisionFileSemanticError, match="actor independence"):
        validate_semantics(document)


def test_non_read_only_action_requires_mandatory_approver_review() -> None:
    document = action_case()
    document["review_requirements"] = []
    document["approvals"] = []
    with pytest.raises(DecisionFileSemanticError, match="mandatory APPROVER review"):
        validate_semantics(document)


def test_unapproved_v0_1_file_migrates_without_inventing_action_or_requester() -> None:
    document = load_decision_file(ROOT / "examples" / "decision-cases" / "low-risk-pass.json")
    legacy = dict(document)
    legacy["schema_version"] = "0.1.0"
    legacy.pop("requested_by")
    legacy.pop("canonical_action")
    migrated = migrate_decision_file_v0_1_to_v0_2(legacy)
    assert migrated["schema_version"] == "0.2.0"
    assert migrated["requested_by"] == migrated["created_by"]
    assert migrated["canonical_action"] is None


def test_v0_1_approval_requires_independent_reapproval() -> None:
    legacy = {"schema_version": "0.1.0", "approvals": [{"legacy": True}]}
    with pytest.raises(DecisionFileSemanticError, match="independent re-approval"):
        migrate_decision_file_v0_1_to_v0_2(legacy)
