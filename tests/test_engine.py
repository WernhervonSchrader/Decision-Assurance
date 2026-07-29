from datetime import datetime, timezone
from itertools import pairwise

import pytest

from decision_assurance import DecisionAssuranceEngine, Outcome
from decision_assurance.audit import payload_hash
from decision_assurance.validation import ContractValidationError, ContractValidator

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)


def engine() -> DecisionAssuranceEngine:
    return DecisionAssuranceEngine(clock=lambda: NOW)


def test_block_takes_precedence_over_review() -> None:
    result = engine().assess(
        {
            "decision_id": "D-1",
            "evidence": [{"id": "E-1", "outdated": True}],
            "constraints": [{"id": "C-1", "hard": True, "satisfied": False}],
        }
    )
    assert result.outcome is Outcome.BLOCK
    assert result.reason_codes == (
        "EVIDENCE_OUTDATED",
        "HARD_CONSTRAINT_VIOLATION",
    )
    assert result.human_review is False


def test_pass_report_has_required_versions_and_audit_reference() -> None:
    result = engine().assess({"decision_id": "D-2", "evidence": []})
    assert result.report["outcome"] == "PASS"
    assert result.report["versions"] == {
        "das": "0.1.0",
        "policy": "unspecified",
        "engine": "0.1.0",
    }
    assert result.report["audit_ref"] == "D-2:audit"


def test_audit_events_form_a_hash_chain() -> None:
    events = engine().assess({"decision_id": "D-3"}).audit_events
    assert events[0]["previous_event_hash"] is None
    for previous, current in pairwise(events):
        assert current["previous_event_hash"] == payload_hash(previous)


def test_report_and_audit_events_match_public_contracts() -> None:
    result = engine().assess({"decision_id": "D-4"})
    validator = ContractValidator()
    validator.validate("assurance-report", result.report)
    for event in result.audit_events:
        validator.validate("audit-event", event)


def test_contract_validator_rejects_unknown_fields() -> None:
    with pytest.raises(ContractValidationError, match="Additional properties"):
        ContractValidator().validate(
            "decision-contract",
            {
                "decision_id": "D-5",
                "decision_type": "QUOTE",
                "requested_action": "APPROVE",
                "created_at": NOW.isoformat(),
                "unexpected": True,
            },
        )


def test_duplicate_reason_codes_are_reported_once() -> None:
    result = engine().assess(
        {
            "decision_id": "D-6",
            "evidence": [
                {"id": "E-1", "outdated": True},
                {"id": "E-2", "outdated": True},
            ],
        }
    )
    assert result.reason_codes == ("EVIDENCE_OUTDATED",)
    assert len(result.findings) == 2
