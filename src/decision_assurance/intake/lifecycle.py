from __future__ import annotations

from .contracts import IntakeStatus


class IntakeTransitionRejected(ValueError):
    pass


_ALLOWED = {
    (IntakeStatus.RECEIVED, IntakeStatus.EXTRACTED),
    (IntakeStatus.EXTRACTED, IntakeStatus.NEEDS_CONFIRMATION),
    (IntakeStatus.EXTRACTED, IntakeStatus.READY),
    (IntakeStatus.NEEDS_CONFIRMATION, IntakeStatus.READY),
    (IntakeStatus.READY, IntakeStatus.COMPILED),
}


def next_status(source: IntakeStatus, target: IntakeStatus, *, ready: bool) -> IntakeStatus:
    if target is IntakeStatus.REJECTED and source not in {
        IntakeStatus.COMPILED,
        IntakeStatus.REJECTED,
    }:
        return target
    if (source, target) not in _ALLOWED:
        raise IntakeTransitionRejected("INTAKE_TRANSITION_NOT_ALLOWED")
    if target is IntakeStatus.READY and not ready:
        raise IntakeTransitionRejected("INTAKE_NOT_READY")
    return target
