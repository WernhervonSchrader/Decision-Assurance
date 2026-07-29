from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from ..authorization import AuthorizationDenied, Permission, authorize
from ..identity import ActorKind, Identity
from .contracts import HumanConfirmation, VerificationReport, VerificationStatus


class ConfirmationRejected(ValueError):
    pass


def confirm_fact(
    report: VerificationReport,
    fact_id: str,
    *,
    action: str,
    new_value: str | None,
    reason: str,
    occurred_at: str,
    identity: Identity,
) -> tuple[VerificationReport, HumanConfirmation]:
    if identity.kind is not ActorKind.HUMAN:
        raise ConfirmationRejected("HUMAN_ACTOR_REQUIRED")
    try:
        authorize(identity, Permission.INTAKE_CONFIRM)
    except AuthorizationDenied as error:
        raise ConfirmationRejected("INTAKE_CONFIRMATION_FORBIDDEN") from error
    if action not in {"CONFIRM", "CORRECT", "REJECT"}:
        raise ConfirmationRejected("INVALID_CONFIRMATION_ACTION")
    if action == "CORRECT" and not new_value:
        raise ConfirmationRejected("CORRECTED_VALUE_REQUIRED")
    if not reason.strip():
        raise ConfirmationRejected("CONFIRMATION_REASON_REQUIRED")
    try:
        current = next(candidate for candidate in report.candidates if candidate.fact_id == fact_id)
    except StopIteration as error:
        raise ConfirmationRejected("FACT_NOT_FOUND") from error

    payload = {
        "intake_id": report.intake_id,
        "fact_id": fact_id,
        "action": action,
        "actor_id": identity.actor_id,
        "new_value": new_value,
        "reason": reason,
        "occurred_at": occurred_at,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:24]
    confirmation = HumanConfirmation(
        f"{report.intake_id}:confirmation:{digest}",
        fact_id,
        action,
        identity.actor_id,
        current.normalized_value,
        new_value,
        reason,
        occurred_at,
    )
    status = (
        VerificationStatus.REJECTED if action == "REJECT" else VerificationStatus.HUMAN_CONFIRMED
    )
    updated_fact = replace(
        current,
        normalized_value=new_value if action == "CORRECT" else current.normalized_value,
        verification_status=status,
        confirmation_required=False,
        confirmed_by_actor_id=identity.actor_id,
        confirmed_by_role=identity.role.value,
    )
    candidates = tuple(
        updated_fact if candidate.fact_id == fact_id else candidate
        for candidate in report.candidates
    )
    still_unresolved = any(
        candidate.confirmation_required
        and candidate.verification_status is VerificationStatus.UNRESOLVED
        for candidate in candidates
    )
    reason_codes = tuple(
        code
        for code in report.reason_codes
        if code != "HUMAN_CONFIRMATION_REQUIRED" or still_unresolved
    )
    if action == "CORRECT" and "REVERIFICATION_REQUIRED" not in reason_codes:
        reason_codes = (*reason_codes, "REVERIFICATION_REQUIRED")
    ready = not reason_codes and not report.findings and not report.unresolved_requirement_refs
    return replace(
        report, candidates=candidates, reason_codes=reason_codes, ready=ready
    ), confirmation
