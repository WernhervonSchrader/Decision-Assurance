from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ...authorization import Permission
from ...export.service import ExportRejected, PilotExportService
from ...identity import Identity
from ...lifecycle.service import LifecycleConflict, PilotLifecycleService
from ..dependencies import get_identity, require, require_idempotency_key
from ..errors import ApiError


def _metric(request: Request, name: str, status: str) -> None:
    metrics = request.app.state.metrics
    if metrics is not None:
        metrics.increment(name, labels={"status": status})


router = APIRouter(prefix="/v1", tags=["pilot"])


@router.get("/session")
def get_session(identity: Identity = Depends(get_identity)) -> dict[str, object]:
    return {
        "actor_id": identity.actor_id,
        "tenant_id": identity.tenant.tenant_id,
        "actor_kind": identity.kind.value,
        "roles": sorted(role.value for role in identity.roles),
    }


class ReasonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")


def _export_service(request: Request) -> PilotExportService:
    service = cast(PilotExportService | None, request.app.state.export_service)
    if service is None:
        raise ApiError(404, "NOT_FOUND")
    return service


def _lifecycle_service(request: Request) -> PilotLifecycleService:
    service = cast(PilotLifecycleService | None, request.app.state.lifecycle_service)
    if service is None:
        raise ApiError(404, "NOT_FOUND")
    return service


@router.get("/decisions/{decision_id}/export")
def export_decision(
    request: Request,
    decision_id: str,
    identity: Identity = Depends(get_identity),
) -> StreamingResponse:
    require(request, identity, Permission.PILOT_EXPORT)
    try:
        archive = _export_service(request).build(identity, decision_id)
    except ExportRejected as error:
        raise ApiError(404, "NOT_FOUND") from error
    except ValueError as error:
        if request.app.state.metrics is not None:
            request.app.state.metrics.increment("export_signature_failures_total")
        raise ApiError(503, "PILOT_EXPORT_UNAVAILABLE") from error
    return StreamingResponse(
        iter((archive.content,)),
        media_type=archive.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{archive.filename}"',
            "Content-Length": str(len(archive.content)),
        },
    )


@router.post("/decisions/{decision_id}/deletion-requests", status_code=202)
def request_deletion(
    request: Request,
    decision_id: str,
    payload: ReasonRequest,
    identity: Identity = Depends(get_identity),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, object]:
    require(request, identity, Permission.DATA_DELETE)
    key = require_idempotency_key(idempotency_key)
    try:
        result = _lifecycle_service(request).request_deletion(
            identity,
            decision_id,
            payload.reason_code,
            key,
            request.state.correlation_id,
        )
    except LifecycleConflict as error:
        code = "NOT_FOUND" if str(error) == "CASE_NOT_FOUND" else "CONFLICT"
        raise ApiError(404 if code == "NOT_FOUND" else 409, code) from error
    _metric(request, "pilot_lifecycle_total", result.status.value.lower())
    if request.app.state.metrics is not None:
        request.app.state.metrics.increment(
            "deletion_activity_total", labels={"status": result.status.value.lower()}
        )
    if result.status.value == "BLOCKED_BY_HOLD" and request.app.state.metrics is not None:
        request.app.state.metrics.increment("legal_hold_violation_attempts_total")
    return result.to_dict()


@router.post("/deletion-requests/{request_id}/execute")
def execute_deletion(
    request: Request,
    request_id: str,
    identity: Identity = Depends(get_identity),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, object]:
    require(request, identity, Permission.DATA_DELETE)
    require_idempotency_key(idempotency_key)
    try:
        result = _lifecycle_service(request).execute_deletion(
            identity, request_id, request.state.correlation_id
        )
    except LifecycleConflict as error:
        raise ApiError(404, "NOT_FOUND") from error
    _metric(request, "pilot_lifecycle_total", result.status.value.lower())
    if request.app.state.metrics is not None:
        request.app.state.metrics.increment(
            "deletion_activity_total", labels={"status": result.status.value.lower()}
        )
    if result.status.value == "BLOCKED_BY_HOLD" and request.app.state.metrics is not None:
        request.app.state.metrics.increment("legal_hold_violation_attempts_total")
    return result.to_dict()


@router.put("/decisions/{decision_id}/legal-hold", status_code=204)
def place_legal_hold(
    request: Request,
    decision_id: str,
    payload: ReasonRequest,
    identity: Identity = Depends(get_identity),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Response:
    require(request, identity, Permission.LEGAL_HOLD_MANAGE)
    require_idempotency_key(idempotency_key)
    try:
        _lifecycle_service(request).place_legal_hold(
            identity, decision_id, payload.reason_code, request.state.correlation_id
        )
    except LifecycleConflict as error:
        raise ApiError(404, "NOT_FOUND") from error
    return Response(status_code=204)


@router.delete("/decisions/{decision_id}/legal-hold", status_code=204)
def release_legal_hold(
    request: Request,
    decision_id: str,
    identity: Identity = Depends(get_identity),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Response:
    require(request, identity, Permission.LEGAL_HOLD_MANAGE)
    require_idempotency_key(idempotency_key)
    if not _lifecycle_service(request).release_legal_hold(
        identity, decision_id, request.state.correlation_id
    ):
        raise ApiError(404, "NOT_FOUND")
    return Response(status_code=204)
