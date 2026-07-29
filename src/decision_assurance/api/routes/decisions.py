from __future__ import annotations

import copy
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response

from ...audit import payload_hash
from ...authorization import Permission
from ...decision_file import evaluate_decision_file, validate_semantics
from ...identity import Identity
from ...repositories.sqlite import IdempotencyConflict
from ...transitions import TransitionPolicy, TransitionRejected
from ...validation import ContractValidationError, ContractValidator
from ..dependencies import get_identity, require, require_idempotency_key
from ..errors import ApiError
from ..schemas import AuditPage, TransitionRequest


router = APIRouter(prefix="/v1/decisions", tags=["decisions"])


def _repository(request: Request):
    return request.app.state.repository


def _operation(
    request: Request, identity: Identity, key: str, operation: str, payload: Any
) -> tuple[str, tuple[int, dict[str, Any]] | None]:
    digest = payload_hash(payload)
    try:
        replay = _repository(request).get_idempotency(
            identity.tenant, identity.actor_id, operation, key, digest
        )
    except IdempotencyConflict as error:
        raise ApiError(409, "CONFLICT", {"reason_code": "IDEMPOTENCY_KEY_REUSED"}) from error
    return digest, replay


def _store_operation(
    request: Request, identity: Identity, key: str, operation: str,
    digest: str, status: int, body: dict[str, Any]
) -> None:
    _repository(request).store_idempotency(
        identity.tenant, identity.actor_id, operation, key, digest, status, body
    )


def _actor(identity: Identity) -> dict[str, str]:
    return {"id": identity.actor_id, "role": identity.role.value, "kind": identity.kind.value}


@router.post("", status_code=201)
async def create_decision(
    request: Request,
    response: Response,
    identity: Identity = Depends(get_identity),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    require(identity, Permission.DECISION_CREATE)
    key = require_idempotency_key(idempotency_key)
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ApiError(422, "INVALID_REQUEST") from error
    digest, replay = _operation(request, identity, key, "decision:create", body)
    if replay:
        response.status_code = replay[0]
        return replay[1]
    try:
        ContractValidator().validate("decision-file", body)
        validate_semantics(body)
    except (ContractValidationError, ValueError) as error:
        raise ApiError(422, "INVALID_REQUEST", {"validation": str(error)}) from error
    if body["created_by"] != _actor(identity):
        raise ApiError(403, "FORBIDDEN", {"reason_code": "ACTOR_SPOOFING"})
    document = copy.deepcopy(body)
    event = {
        "event_id": f"{document['decision_id']}:created:1",
        "event_type": "decision.created",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "actor": _actor(identity),
        "from_status": None,
        "to_status": "DRAFT",
        "reason_codes": ["DECISION_CREATED"],
        "payload_hash": payload_hash(body),
        "previous_event_hash": None,
        "tenant_id": identity.tenant.tenant_id,
        "correlation_id": request.state.correlation_id,
        "source_channel": "api",
    }
    document["audit_events"].append(event)
    try:
        _repository(request).create_decision(identity.tenant, document)
        _repository(request).save_result(identity.tenant, document, None, [event])
    except sqlite3.IntegrityError as error:
        raise ApiError(409, "CONFLICT", {"reason_code": "DECISION_ALREADY_EXISTS"}) from error
    result = document
    _store_operation(request, identity, key, "decision:create", digest, 201, result)
    return result


@router.get("/{decision_id}")
def get_decision(request: Request, decision_id: str, identity: Identity = Depends(get_identity)) -> dict[str, Any]:
    require(identity, Permission.DECISION_READ)
    document = _repository(request).get_decision(identity.tenant, decision_id)
    if document is None:
        raise ApiError(404, "NOT_FOUND")
    return document


@router.post("/{decision_id}/evaluate")
def evaluate(
    request: Request, response: Response, decision_id: str,
    identity: Identity = Depends(get_identity),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    require(identity, Permission.DECISION_EVALUATE)
    key = require_idempotency_key(idempotency_key)
    digest, replay = _operation(request, identity, key, f"decision:evaluate:{decision_id}", {})
    if replay:
        response.status_code = replay[0]
        return replay[1]
    document = _repository(request).get_decision(identity.tenant, decision_id)
    if document is None:
        raise ApiError(404, "NOT_FOUND")
    before = len(document["audit_events"])
    updated, result = evaluate_decision_file(document)
    new_events = updated["audit_events"][before:]
    for event in new_events:
        event.update({"tenant_id": identity.tenant.tenant_id, "correlation_id": request.state.correlation_id, "source_channel": "api"})
    _repository(request).save_result(identity.tenant, updated, result.report, new_events)
    body = result.report
    _store_operation(request, identity, key, f"decision:evaluate:{decision_id}", digest, 200, body)
    return body


@router.post("/{decision_id}/transitions")
def transition(
    request: Request, response: Response, decision_id: str, transition_request: TransitionRequest,
    identity: Identity = Depends(get_identity),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    key = require_idempotency_key(idempotency_key)
    document = _repository(request).get_decision(identity.tenant, decision_id)
    if document is None:
        raise ApiError(404, "NOT_FOUND")
    is_approval_action = transition_request.target == "APPROVED" or (
        transition_request.target == "BLOCKED" and document["status"] == "REVIEW"
    )
    require(identity, Permission.DECISION_APPROVE if is_approval_action else Permission.DECISION_VALIDATE)
    operation = f"decision:transition:{decision_id}:{transition_request.target}"
    digest, replay = _operation(request, identity, key, operation, transition_request.model_dump())
    if replay:
        response.status_code = replay[0]
        return replay[1]
    try:
        updated = TransitionPolicy().transition(document, transition_request.target, _actor(identity))
    except TransitionRejected as error:
        raise ApiError(409, "CONFLICT", {"reason_codes": error.reason_codes}) from error
    event = updated["audit_events"][-1]
    event.update({"tenant_id": identity.tenant.tenant_id, "correlation_id": request.state.correlation_id, "source_channel": "api"})
    _repository(request).save_result(identity.tenant, updated, None, [event])
    _store_operation(request, identity, key, operation, digest, 200, updated)
    return updated


@router.get("/{decision_id}/report")
def get_report(request: Request, decision_id: str, identity: Identity = Depends(get_identity)) -> dict[str, Any]:
    require(identity, Permission.REPORT_READ)
    report = _repository(request).get_report(identity.tenant, decision_id)
    if report is None:
        raise ApiError(404, "NOT_FOUND")
    return report


@router.get("/{decision_id}/audit", response_model=AuditPage)
def get_audit(
    request: Request, decision_id: str, identity: Identity = Depends(get_identity),
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    require(identity, Permission.AUDIT_READ)
    if _repository(request).get_decision(identity.tenant, decision_id) is None:
        raise ApiError(404, "NOT_FOUND")
    return {"items": _repository(request).list_audit(identity.tenant, decision_id, limit=limit, offset=offset), "limit": limit, "offset": offset}
