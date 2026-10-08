from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, Request

from ...authorization import Permission
from ...identity import Identity
from ...strategy.contracts import ImportEnvelope
from ...strategy.store import StrategyStore
from ..dependencies import get_identity, require
from ..errors import ApiError

router = APIRouter(prefix="/v1/strategy", tags=["strategy"])


def _store(request: Request) -> StrategyStore:
    return cast(StrategyStore, request.app.state.strategy_store)


def _error(error: ValueError) -> ApiError:
    reason = str(error)
    if reason == "STRATEGY_DECISION_NOT_FOUND":
        return ApiError(404, "NOT_FOUND")
    if reason in {
        "STRATEGY_DOCUMENT_CHANGED",
        "STRATEGY_DECISION_NOT_DRAFT",
        "STRATEGY_EVALUATED_DRAFT_REQUIRES_NEW_CASE",
        "STRATEGY_ARTIFACT_ID_REUSED",
        "STRATEGY_BASELINE_IMMUTABLE",
        "STRATEGY_BASELINE_CORRECTION_BRANCH",
    }:
        return ApiError(409, "CONFLICT", {"reason_code": reason})
    # Do not echo external JSON-schema messages or source text in errors.
    return ApiError(422, "INVALID_REQUEST", {"reason_code": "STRATEGY_CONTRACT_INVALID"})


@router.post("/preview")
def preview(
    body: ImportEnvelope, request: Request, identity: Identity = Depends(get_identity)
) -> dict[str, Any]:
    require(request, identity, Permission.DECISION_READ)
    try:
        return _store(request).preview(identity, body)
    except PermissionError as error:
        raise ApiError(403, "FORBIDDEN") from error
    except ValueError as error:
        raise _error(error) from error


@router.post("/imports")
def import_artifact(
    body: ImportEnvelope, request: Request, identity: Identity = Depends(get_identity)
) -> dict[str, Any]:
    require(request, identity, Permission.DECISION_CREATE)
    try:
        return _store(request).import_artifact(identity, body, request.state.correlation_id)
    except PermissionError as error:
        raise ApiError(403, "FORBIDDEN") from error
    except ValueError as error:
        raise _error(error) from error


@router.get("/artifacts/{artifact_id}")
def get_artifact(
    artifact_id: str, request: Request, identity: Identity = Depends(get_identity)
) -> dict[str, Any]:
    require(request, identity, Permission.DECISION_READ)
    record = _store(request).get(identity, artifact_id)
    if record is None:
        raise ApiError(404, "NOT_FOUND")
    return record
