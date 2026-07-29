from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

from fastapi import APIRouter, Depends, Header, Request

from ...audit import payload_hash
from ...authorization import Permission
from ...identity import Identity
from ...intake.codec import to_dict, verification_from_dict
from ...intake.compiler import CompilationRejected, DecisionFileCompiler
from ...intake.confirmation import ConfirmationRejected, confirm_fact
from ...intake.extractor import DeterministicQuoteExtractor
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
    require(identity, Permission.INTAKE_CREATE)
    operation = f"intake:create:{body.intake_id}"
    key, digest, replay = _begin(request, identity, operation, idempotency_key, body.model_dump())
    if replay is not None:
        return replay
    existing = _intakes(request).get(identity.tenant, body.intake_id)
    if existing is not None:
        if existing.get("raw_input") != body.raw_input:
            raise ApiError(409, "CONFLICT", {"reason_code": "INTAKE_ALREADY_EXISTS"})
        return existing
    extraction = DeterministicQuoteExtractor().extract(
        body.raw_input, locale=body.locale, intake_id=body.intake_id
    )
    verification = IntakeVerifier(_policies(request)).verify(identity.tenant.tenant_id, extraction)
    record: dict[str, Any] = {
        "schema_version": "0.3.0",
        "intake_id": body.intake_id,
        "status": "READY" if verification.ready else "NEEDS_CONFIRMATION",
        "raw_input": body.raw_input,
        "raw_input_hash": extraction.candidates[0].source.content_hash
        if extraction.candidates
        else None,
        "locale": body.locale,
        "contract_ready": verification.ready,
        "extraction": to_dict(extraction),
        "verification": to_dict(verification),
        "confirmations": [],
        "compiled_decision_id": None,
    }
    _intakes(request).put(identity.tenant, body.intake_id, record["status"], record)
    _finish(request, identity, operation, key, digest, record)
    return record


@router.get("/{intake_id}")
def get_intake(
    intake_id: str, request: Request, identity: Identity = Depends(get_identity)
) -> dict[str, Any]:
    require(identity, Permission.INTAKE_READ)
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
    require(identity, Permission.INTAKE_CONFIRM)
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
    except ConfirmationRejected as error:
        raise ApiError(409, "CONFLICT", {"reason_code": str(error)}) from error
    confirmations = record.setdefault("confirmations", [])
    serialized = to_dict(confirmation)
    if not any(item["confirmation_id"] == confirmation.confirmation_id for item in confirmations):
        confirmations.append(serialized)
    record["verification"] = to_dict(updated)
    record["contract_ready"] = updated.ready
    record["status"] = "READY" if updated.ready else "NEEDS_CONFIRMATION"
    _intakes(request).put(identity.tenant, intake_id, record["status"], record)
    _finish(request, identity, operation, key, digest, record)
    return record


@router.post("/{intake_id}/compile", status_code=201)
def compile_intake(
    intake_id: str,
    request: Request,
    identity: Identity = Depends(get_identity),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    require(identity, Permission.INTAKE_COMPILE)
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
            return decision
    try:
        decision = DecisionFileCompiler().compile(
            verification_from_dict(record["verification"]),
            policy=policy,
            actor_id="system:intake-compiler",
        )
    except CompilationRejected as error:
        raise ApiError(409, "CONFLICT", {"reason_code": str(error)}) from error
    _decisions(request).create_decision(identity.tenant, decision, list(decision["audit_events"]))
    record["compiled_decision_id"] = decision["decision_id"]
    record["status"] = "COMPILED"
    _intakes(request).put(identity.tenant, intake_id, "COMPILED", record)
    _finish(request, identity, operation, key, digest, decision)
    return decision
