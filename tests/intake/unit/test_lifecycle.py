import pytest

from decision_assurance.intake.contracts import IntakeStatus
from decision_assurance.intake.lifecycle import IntakeTransitionRejected, next_status


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("RECEIVED", "EXTRACTED"),
        ("EXTRACTED", "NEEDS_CONFIRMATION"),
        ("EXTRACTED", "READY"),
        ("NEEDS_CONFIRMATION", "READY"),
        ("READY", "NEEDS_CONFIRMATION"),
        ("READY", "COMPILED"),
        ("RECEIVED", "REJECTED"),
    ],
)
def test_allowed_intake_transitions(source: str, target: str) -> None:
    assert next_status(
        IntakeStatus(source), IntakeStatus(target), ready=target == "READY"
    ) is IntakeStatus(target)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("RECEIVED", "READY"),
        ("NEEDS_CONFIRMATION", "COMPILED"),
        ("COMPILED", "READY"),
        ("REJECTED", "EXTRACTED"),
    ],
)
def test_prohibited_intake_transitions(source: str, target: str) -> None:
    with pytest.raises(IntakeTransitionRejected):
        next_status(IntakeStatus(source), IntakeStatus(target), ready=False)


def test_ready_requires_resolved_mandatory_facts() -> None:
    with pytest.raises(IntakeTransitionRejected, match="INTAKE_NOT_READY"):
        next_status(IntakeStatus.EXTRACTED, IntakeStatus.READY, ready=False)
