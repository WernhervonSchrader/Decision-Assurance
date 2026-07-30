from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, Header, Query, Request, Response

from ...audit import payload_hash
from ...authorization import Permission
from ...identity import Identity
from ...repositories.protocols import DecisionRepository
from ...web_research.contracts import ResearchRun
from ...web_research.lifecycle import ResearchTransitionRejected
from ...web_research.orchestrator import ResearchOrchestrator
from ...web_research.repository import ResearchIdempotencyConflict, SqliteResearchRepository
from ..dependencies import get_identity, require, require_idempotency_key
from ..errors import ApiError
from ..research_schemas import EmptyResearchAction, ResearchRequestBody

router = APIRouter(prefix="/v1/research-runs", tags=["research"])


def _research(request: Request) -> SqliteResearchRepository:
    return cast(SqliteResearchRepository, request.app.state.research_repository)


def _orchestrator(request: Request) -> ResearchOrchestrator:
    return cast(ResearchOrchestrator, request.app.state.research_orchestrator)


def _decisions(request: Request) -> DecisionRepository:
    return cast(DecisionRepository, request.app.state.repository)


def _begin(
    request: Request,
    identity: Identity,
    operation: str,
    key_value: str | None,
    payload: Any,
) -> tuple[str, str, tuple[int, dict[str, Any]] | None]:
    key = require_idempotency_key(key_value)
    digest = payload_hash(payload)
    try:
        replay = _research(request).get_idempotency(
            identity.tenant, identity.actor_id, operation, key, digest
        )
    except ResearchIdempotencyConflict as error:
        raise ApiError(409, "CONFLICT", {"reason_code": "IDEMPOTENCY_KEY_REUSED"}) from error
    return key, digest, replay


def _finish(
    request: Request,
    identity: Identity,
    operation: str,
    key: str,
    digest: str,
    status: int,
    body: dict[str, Any],
) -> None:
    _research(request).store_idempotency(
        identity.tenant, identity.actor_id, operation, key, digest, status, body
    )


def _summary(run: ResearchRun) -> dict[str, Any]:
    return {
        "schema_version": "0.4.0",
        "research_run_id": run.research_run_id,
        "decision_file_id": run.request.decision_file_id,
        "status": run.status.value,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "correlation_id": run.correlation_id,
        "source_count": len(run.sources),
        "evidence_count": len(run.evidence),
        "provider_cost_units": run.provider_cost_units,
        "compiled_decision_file_id": run.compiled_decision_file_id,
        "errors": [
            {
                "reason_code": item.reason_code,
                "source_id": item.source_id,
                "provider_id": item.provider.provider_id if item.provider else None,
                "retryable": item.provider.retryable if item.provider else False,
                "status_code": item.provider.status_code if item.provider else None,
            }
            for item in run.errors
        ],
    }


def _required(request: Request, identity: Identity, run_id: str) -> ResearchRun:
    run = _research(request).get(identity.tenant, run_id)
    if run is None:
        raise ApiError(404, "NOT_FOUND")
    return run


@router.post("", status_code=201)
async def create_research_run(
    body: ResearchRequestBody,
    request: Request,
    response: Response,
    identity: Identity = Depends(get_identity),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    require(identity, Permission.RESEARCH_CREATE)
    if body.force_refresh:
        require(identity, Permission.RESEARCH_FORCE_REFRESH)
    operation = "research:create"
    payload = body.model_dump(mode="json")
    key, digest, replay = _begin(request, identity, operation, idempotency_key, payload)
    if replay:
        response.status_code = replay[0]
        return replay[1]
    document = _decisions(request).get_decision(identity.tenant, body.decision_file_id)
    if document is None:
        raise ApiError(404, "NOT_FOUND")
    if document["status"] != "DRAFT":
        raise ApiError(409, "CONFLICT", {"reason_code": "DECISION_NOT_DRAFT"})
    claim_ids = {item["id"] for item in document["claims"]}
    if not set(body.claim_refs).issubset(claim_ids):
        raise ApiError(422, "INVALID_REQUEST", {"reason_code": "CLAIM_REFERENCE_NOT_FOUND"})
    try:
        run = await _orchestrator(request).execute(
            identity.tenant,
            identity.actor_id,
            body.to_contract(),
            payload_hash(document),
            request.state.correlation_id,
            refresh_generation=body.refresh_generation,
        )
    except ValueError as error:
        raise ApiError(422, "INVALID_REQUEST", {"reason_code": str(error)}) from error
    result = _summary(run)
    _finish(request, identity, operation, key, digest, 201, result)
    return result


@router.get("/{research_run_id}")
def get_research_run(
    research_run_id: str,
    request: Request,
    identity: Identity = Depends(get_identity),
) -> dict[str, Any]:
    require(identity, Permission.RESEARCH_READ)
    return _summary(_required(request, identity, research_run_id))


@router.get("/{research_run_id}/sources")
def get_research_sources(
    research_run_id: str,
    request: Request,
    identity: Identity = Depends(get_identity),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    require(identity, Permission.RESEARCH_READ)
    _required(request, identity, research_run_id)
    return {
        "items": _research(request).list_sources(
            identity.tenant, research_run_id, limit=limit, offset=offset
        ),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{research_run_id}/evidence")
def get_research_evidence(
    research_run_id: str,
    request: Request,
    identity: Identity = Depends(get_identity),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    require(identity, Permission.RESEARCH_READ)
    _required(request, identity, research_run_id)
    return {
        "items": _research(request).list_evidence(
            identity.tenant, research_run_id, limit=limit, offset=offset
        ),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{research_run_id}/audit")
def get_research_audit(
    research_run_id: str,
    request: Request,
    identity: Identity = Depends(get_identity),
) -> dict[str, Any]:
    require(identity, Permission.RESEARCH_AUDIT_READ)
    _required(request, identity, research_run_id)
    return {"items": _research(request).list_audit(identity.tenant, research_run_id)}


async def _action(
    action: str,
    research_run_id: str,
    body: EmptyResearchAction,
    request: Request,
    response: Response,
    identity: Identity,
    idempotency_key: str | None,
) -> dict[str, Any]:
    permission = Permission.RESEARCH_RETRY if action == "retry" else Permission.RESEARCH_CANCEL
    require(identity, permission)
    _required(request, identity, research_run_id)
    operation = f"research:{action}:{research_run_id}"
    payload = body.model_dump(mode="json")
    key, digest, replay = _begin(request, identity, operation, idempotency_key, payload)
    if replay:
        response.status_code = replay[0]
        return replay[1]
    try:
        if action == "retry":
            run = await _orchestrator(request).retry(
                identity.tenant, identity.actor_id, research_run_id, request.state.correlation_id
            )
        else:
            run = _orchestrator(request).cancel(
                identity.tenant, identity.actor_id, research_run_id, request.state.correlation_id
            )
    except (ResearchTransitionRejected, ValueError) as error:
        raise ApiError(409, "CONFLICT", {"reason_code": str(error)}) from error
    result = _summary(run)
    _finish(request, identity, operation, key, digest, 200, result)
    return result


@router.post("/{research_run_id}/retry")
async def retry_research_run(
    research_run_id: str,
    body: EmptyResearchAction,
    request: Request,
    response: Response,
    identity: Identity = Depends(get_identity),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    return await _action(
        "retry", research_run_id, body, request, response, identity, idempotency_key
    )


@router.post("/{research_run_id}/cancel")
async def cancel_research_run(
    research_run_id: str,
    body: EmptyResearchAction,
    request: Request,
    response: Response,
    identity: Identity = Depends(get_identity),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    return await _action(
        "cancel", research_run_id, body, request, response, identity, idempotency_key
    )
