from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import pytest

from decision_assurance.production import GateResult, ReleaseStatus
from decision_assurance.release_verification import (
    MANDATORY_GATES,
    ReleaseVerifier,
    publication_eligible,
    report_to_dict,
)

COMMIT_SHA = "a" * 40


def _passing_gates() -> tuple[GateResult, ...]:
    return tuple(
        GateResult(gate_id, ReleaseStatus.PASS, (), (f"evidence/{gate_id}.json",))
        for gate_id in MANDATORY_GATES
    )


def test_complete_pass_report_is_publication_eligible() -> None:
    report = ReleaseVerifier().verify(
        version="0.5.0",
        commit_sha=COMMIT_SHA,
        generated_at=datetime.now(timezone.utc).isoformat(),
        gates=_passing_gates(),
    )

    assert report.status is ReleaseStatus.PASS
    assert publication_eligible(report)


def test_missing_mandatory_gate_fails_closed() -> None:
    report = ReleaseVerifier().verify(
        version="0.5.0",
        commit_sha=COMMIT_SHA,
        generated_at="2026-07-30T12:00:00Z",
        gates=_passing_gates()[:-1],
    )

    assert report.status is ReleaseStatus.BLOCK
    assert not publication_eligible(report)
    assert report.gates[-1].reason_codes == ("MANDATORY_GATE_MISSING",)


@pytest.mark.parametrize(
    "reason_code",
    [
        "TENANT_ISOLATION_FAILURE",
        "CRITICAL_VULNERABILITY",
        "MIGRATION_FAILURE",
        "RESTORE_FAILURE",
        "AUDIT_INTEGRITY_FAILURE",
        "STATIC_AUTH_PRODUCTION",
        "RESEARCH_OUTCOME_USED",
        "AGENT_APPROVAL",
        "SECRET_LEAKAGE",
    ],
)
def test_blocking_reason_cannot_be_downgraded(reason_code: str) -> None:
    gates = list(_passing_gates())
    gates[0] = GateResult(
        gates[0].gate_id,
        ReleaseStatus.REVIEW,
        (reason_code,),
        ("evidence/injected-failure.json",),
    )

    report = ReleaseVerifier().verify(
        version="0.5.0",
        commit_sha=COMMIT_SHA,
        generated_at="2026-07-30T12:00:00Z",
        gates=tuple(gates),
    )

    assert report.gates[0].status is ReleaseStatus.BLOCK
    assert report.status is ReleaseStatus.BLOCK
    assert not publication_eligible(report)


def test_review_is_not_publication_eligible() -> None:
    gates = list(_passing_gates())
    gates[0] = GateResult(
        gates[0].gate_id,
        ReleaseStatus.REVIEW,
        ("MANUAL_REVIEW_REQUIRED",),
        ("evidence/review.json",),
    )
    report = ReleaseVerifier().verify(
        version="0.5.0",
        commit_sha=COMMIT_SHA,
        generated_at="2026-07-30T12:00:00Z",
        gates=tuple(gates),
    )

    assert report.status is ReleaseStatus.REVIEW
    assert not publication_eligible(report)


def test_report_serialization_matches_public_schema() -> None:
    report = ReleaseVerifier().verify(
        version="0.5.0",
        commit_sha=COMMIT_SHA,
        generated_at="2026-07-30T12:00:00Z",
        gates=_passing_gates(),
    )
    schema = json.loads(Path("schemas/production/release-verification.schema.json").read_text())

    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(
        report_to_dict(report)
    )
