from datetime import datetime, timezone
from pathlib import Path

import pytest

from decision_assurance.intake.compiler import CompilationRejected, DecisionFileCompiler
from decision_assurance.intake.contracts import IntakeStatus, PolicyContext
from decision_assurance.intake.extractor import DeterministicQuoteExtractor
from decision_assurance.intake.verification import InMemoryPolicyRegistry, IntakeVerifier
from decision_assurance.validation import ContractValidator

NOW = datetime(2026, 7, 29, 10, 0, tzinfo=timezone.utc)
POLICY = PolicyContext("SALES-1", "1.0", "2026-01-01", "10", "25", 24, "50000")


def verified(raw: str):  # type: ignore[no-untyped-def]
    extraction = DeterministicQuoteExtractor().extract(raw, locale="en", intake_id="I-1")
    return IntakeVerifier(InMemoryPolicyRegistry({"tenant-a": POLICY})).verify(
        "tenant-a", extraction
    )


def test_compiler_builds_valid_outcome_free_decision_file_idempotently() -> None:
    report = verified("Quote 40,000 EUR, 8% discount and 30% margin.")
    compiler = DecisionFileCompiler(clock=lambda: NOW)
    first = compiler.compile(
        report,
        policy=POLICY,
        actor_id="system:intake-compiler",
        intake_status=IntakeStatus.READY,
    )
    second = compiler.compile(
        report,
        policy=POLICY,
        actor_id="system:intake-compiler",
        intake_status=IntakeStatus.READY,
    )
    assert first == second
    assert first["decision_outcome"] is None
    assert first["outcome_reasons"] == []
    assert all(item["status"] == "VERIFIED" for item in first["evidence"])
    ContractValidator(Path(__file__).parents[3] / "schemas").validate("decision-file", first)


def test_compiler_fails_closed_for_intake_needing_confirmation() -> None:
    report = verified("Quote 40,000 EUR, approved by management.")
    with pytest.raises(CompilationRejected, match="NEEDS_CONFIRMATION"):
        DecisionFileCompiler(clock=lambda: NOW).compile(
            report,
            policy=POLICY,
            actor_id="system:intake-compiler",
            intake_status=IntakeStatus.NEEDS_CONFIRMATION,
        )


def test_compiler_rejects_ready_report_when_lifecycle_is_not_ready() -> None:
    report = verified("Quote 40,000 EUR, 8% discount and 30% margin.")
    assert report.ready
    with pytest.raises(CompilationRejected, match="NEEDS_CONFIRMATION"):
        DecisionFileCompiler(clock=lambda: NOW).compile(
            report,
            policy=POLICY,
            actor_id="system:intake-compiler",
            intake_status=IntakeStatus.EXTRACTED,
        )
