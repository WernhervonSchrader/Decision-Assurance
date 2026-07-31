from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

from fastapi import APIRouter, Depends, Header, Request

from ...audit import payload_hash
from ...authorization import Permission
from ...identity import Identity
from ...intake.audit import intake_audit_event
from ...intake.codec import to_dict, verification_from_dict
from ...intake.compiler import CompilationRejected, DecisionFileCompiler
from ...intake.confirmation import ConfirmationRejected, confirm_fact
from ...intake.contracts import IntakeStatus
from ...intake.extractor import DeterministicQuoteExtractor
from ...intake.lifecycle import IntakeTransitionRejected, next_status
from ...intake.repository import IntakeIdempotencyConflict, IntakeRepository
from ...intake.verification import IntakeVerifier, PolicyRegistry
from ...repositories.protocols import DecisionRepository
from ..dependencies import get_identity, require, require_idempotency_key
from ..errors import ApiError
from ..schemas import IntakeConfirmationBody, IntakeRequestBody

router = APIRouter(prefix="/v1/intakes", tags=["intakes"])


def _intakes(request: Request) -> IntakeRepository:
    return cast(IntakeRepository, request.app.state.intake_repository)


def _policies(request: Request) -> PolicyRegistry:
    return cast(PolicyRegistry, request.app.state.policy_registry)


def _decisions(request: Request) -> DecisionRepository:
    return cast(DecisionRepository, request.app.state.repository)


def _begin(
    request: Request,
    identity: Identity,
    operation: str,
    key_value: str | None,
    payload: Any,
) -> tuple[str, str, dict[str, Any] | None]:
    key = require_idempotency_key(key_value)
    digest = payload_hash(payload)
    try:
        replay = _intakes(request).get_idempotency(
            identity.tenant, identity.actor_id, operation, key, digest
        )
    except IntakeIdempotencyConflict as error:
        raise ApiError(409, "CONFLICT", {"reason_code": "IDEMPOTENCY_KEY_REUSED"}) from error
    return key, digest, replay


def _finish(
    request: Request,
    identity: Identity,
    operation: str,
    key: str,
    digest: str,
    response: dict[str, Any],
) -> None:
    _intakes(request).store_idempotency(
        identity.tenant, identity.actor_id, operation, key, digest, response
    )


@router.post("", status_code=201)
def create_intake(
    body: IntakeRequestBody,
    request: Request,
    identity: Identity = Depends(get_identity),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    require(request, identity, Permission.INTAKE_CREATE)
    operation = f"intake:create:{body.intake_id}"
    key, digest, replay = _begin(request, identity, operation, idempotency_key, body.model_dump())
    if replay is not None:
        return replay
    existing = _intakes(request).get(identity.tenant, body.intake_id)
    if existing is not None:
        if existing.get("raw_input") != body.raw_input:
            raise ApiError(409, "CONFLICT", {"reason_code": "INTAKE_ALREADY_EXISTS"})
        _finish(request, identity, operation, key, digest, existing)
        return existing
    extraction = DeterministicQuoteExtractor().extract(
        body.raw_input, locale=body.locale, intake_id=body.intake_id
    )
    verification = IntakeVerifier(_policies(request)).verify(identity.tenant.tenant_id, extraction)
    occurred_at = datetime.now(timezone.utc).isoformat()
    target_status = IntakeStatus.READY if verification.ready else IntakeStatus.NEEDS_CONFIRMATION
    next_status(IntakeStatus.RECEIVED, IntakeStatus.EXTRACTED, ready=False)
    next_status(IntakeStatus.EXTRACTED, target_status, ready=verification.ready)
    extracted_event = intake_audit_event(
        intake_id=body.intake_id,
        sequence=1,
        event_type="intake.extracted",
        occurred_at=occurred_at,
        actor_id=identity.actor_id,
        from_status=IntakeStatus.RECEIVED,
        to_status=IntakeStatus.EXTRACTED,
        reason_codes=("RAW_INPUT_EXTRACTED",),
        payload=to_dict(extraction),
        previous_event=None,
    )
    status_event = intake_audit_event(
        intake_id=body.intake_id,
        sequence=2,
        event_type="intake.readiness-determined",
        occurred_at=occurred_at,
        actor_id=identity.actor_id,
        from_status=IntakeStatus.EXTRACTED,
        to_status=target_status,
        reason_codes=verification.reason_codes or ("INTAKE_READY",),
        payload=to_dict(verification),
        previous_event=extracted_event,
    )
    record: dict[str, Any] = {
        "schema_version": "0.3.0",
        "intake_id": body.intake_id,
        "status": target_status.value,
        "raw_input": body.raw_input,
        "raw_input_hash": payload_hash(body.raw_input),
        "locale": body.locale,
        "created_at": occurred_at,
        "updated_at": occurred_at,
        "contract_ready": verification.ready,
        "extraction": to_dict(extraction),
        "verification": to_dict(verification),
        "confirmations": [],
        "findings": [to_dict(finding) for finding in verification.findings],
        "audit_events": [extracted_event, status_event],
        "compiled_decision_id": None,
    }
    _intakes(request).save_operation(
        identity.tenant,
        body.intake_id,
        record["status"],
        record,
        facts=[to_dict(candidate) for candidate in verification.candidates],
        confirmation=None,
        events=[extracted_event, status_event],
        idempotency=(identity.actor_id, operation, key, digest, record),
    )
    return record


@router.get("/{intake_id}")
def get_intake(
    intake_id: str, request: Request, identity: Identity = Depends(get_identity)
) -> dict[str, Any]:
    require(request, identity, Permission.INTAKE_READ)
    record = _intakes(request).get(identity.tenant, intake_id)
    if record is None:
        raise ApiError(404, "NOT_FOUND")
    return record


@router.post("/{intake_id}/confirmations")
def add_confirmation(
    intake_id: str,
    body: IntakeConfirmationBody,
    request: Request,
    identity: Identity = Depends(get_identity),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    require(request, identity, Permission.INTAKE_CONFIRM)
    operation = f"intake:confirm:{intake_id}:{body.fact_id}"
    key, digest, replay = _begin(request, identity, operation, idempotency_key, body.model_dump())
    if replay is not None:
        return replay
    record = _intakes(request).get(identity.tenant, intake_id)
    if record is None:
        raise ApiError(404, "NOT_FOUND")
    try:
        updated, confirmation = confirm_fact(
            verification_from_dict(record["verification"]),
            body.fact_id,
            action=body.action,
            new_value=body.new_value,
            reason=body.reason,
            occurred_at=datetime.now(timezone.utc).isoformat(),
            identity=identity,
        )
        updated = IntakeVerifier(_policies(request)).reverify(identity.tenant.tenant_id, updated)
    except ConfirmationRejected as error:
        raise ApiError(409, "CONFLICT", {"reason_code": str(error)}) from error
    source_status = IntakeStatus(record["status"])
    target_status = IntakeStatus.READY if updated.ready else IntakeStatus.NEEDS_CONFIRMATION
    if target_status is not source_status:
        try:
            next_status(source_status, target_status, ready=updated.ready)
        except IntakeTransitionRejected as error:
            raise ApiError(409, "CONFLICT", {"reason_code": str(error)}) from error
    confirmations = record.setdefault("confirmations", [])
    serialized = to_dict(confirmation)
    if not any(item["confirmation_id"] == confirmation.confirmation_id for item in confirmations):
        confirmations.append(serialized)
    record["verification"] = to_dict(updated)
    record["findings"] = [to_dict(finding) for finding in updated.findings]
    record["contract_ready"] = updated.ready
    record["status"] = target_status.value
    record["updated_at"] = confirmation.occurred_at
    audit_events = record.setdefault("audit_events", [])
    confirmation_event = intake_audit_event(
        intake_id=intake_id,
        sequence=len(audit_events) + 1,
        event_type=f"intake.fact-{body.action.lower()}",
        occurred_at=confirmation.occurred_at,
        actor_id=identity.actor_id,
        from_status=source_status,
        to_status=target_status,
        reason_codes=("FACT_HUMAN_CONFIRMED",),
        payload=serialized,
        previous_event=audit_events[-1] if audit_events else None,
    )
    audit_events.append(confirmation_event)
    _intakes(request).save_operation(
        identity.tenant,
        intake_id,
        record["status"],
        record,
        facts=[to_dict(candidate) for candidate in updated.candidates],
        confirmation=serialized,
        events=[confirmation_event],
        idempotency=(identity.actor_id, operation, key, digest, record),
    )
    return record


@router.post("/{intake_id}/compile", status_code=201)
def compile_intake(
    intake_id: str,
    request: Request,
    identity: Identity = Depends(get_identity),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    require(request, identity, Permission.INTAKE_COMPILE)
    operation = f"intake:compile:{intake_id}"
    key, digest, replay = _begin(request, identity, operation, idempotency_key, {})
    if replay is not None:
        return replay
    record = _intakes(request).get(identity.tenant, intake_id)
    if record is None:
        raise ApiError(404, "NOT_FOUND")
    policy = _policies(request).get_active(identity.tenant.tenant_id)
    if policy is None:
        raise ApiError(409, "CONFLICT", {"reason_code": "TRUSTED_POLICY_UNAVAILABLE"})
    if record.get("compiled_decision_id"):
        decision = _decisions(request).get_decision(identity.tenant, record["compiled_decision_id"])
        if decision is not None:
            _finish(request, identity, operation, key, digest, decision)
            return decision
    try:
        current_status = IntakeStatus(record["status"])
        if current_status is not IntakeStatus.READY:
            raise CompilationRejected("NEEDS_CONFIRMATION")
        next_status(current_status, IntakeStatus.COMPILED, ready=True)
        decision = DecisionFileCompiler().compile(
            verification_from_dict(record["verification"]),
            policy=policy,
            actor_id="system:intake-compiler",
            intake_status=current_status,
        )
    except CompilationRejected as error:
        raise ApiError(409, "CONFLICT", {"reason_code": str(error)}) from error
    existing_decision = _decisions(request).get_decision(identity.tenant, decision["decision_id"])
    if existing_decision is None:
        _decisions(request).create_decision(
            identity.tenant, decision, list(decision["audit_events"])
        )
    else:
        decision = existing_decision
    record["compiled_decision_id"] = decision["decision_id"]
    record["status"] = "COMPILED"
    record["updated_at"] = decision["created_at"]
    audit_events = record.setdefault("audit_events", [])
    compiled_event = intake_audit_event(
        intake_id=intake_id,
        sequence=len(audit_events) + 1,
        event_type="intake.compiled",
        occurred_at=decision["created_at"],
        actor_id=identity.actor_id,
        from_status=IntakeStatus.READY,
        to_status=IntakeStatus.COMPILED,
        reason_codes=("VERIFIED_INTAKE_COMPILED",),
        payload={"decision_id": decision["decision_id"]},
        previous_event=audit_events[-1] if audit_events else None,
    )
    audit_events.append(compiled_event)
    _intakes(request).save_operation(
        identity.tenant,
        intake_id,
        "COMPILED",
        record,
        facts=[],
        confirmation=None,
        events=[compiled_event],
        idempotency=(identity.actor_id, operation, key, digest, decision),
    )
    return decision


@router.get("/{intake_id}/audit")
def get_intake_audit(
    intake_id: str, request: Request, identity: Identity = Depends(get_identity)
) -> dict[str, Any]:
    require(request, identity, Permission.AUDIT_READ)
    if _intakes(request).get(identity.tenant, intake_id) is None:
        raise ApiError(404, "NOT_FOUND")
    return {"items": _intakes(request).list_audit(identity.tenant, intake_id)}
