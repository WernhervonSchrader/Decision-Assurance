from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.responses import Response

from ..export.service import PilotExportService
from ..i18n import localize, select_locale
from ..identity import Authenticator
from ..intake.repository import IntakeRepository
from ..intake.verification import PolicyRegistry
from ..lifecycle.service import PilotLifecycleService
from ..observability.health import HealthService
from ..observability.metrics import AssuranceOutcomeCollector
from ..production.contracts import BuildMetadata
from ..production.ports import MetricsPort, StructuredLoggerPort
from ..repositories.protocols import DecisionRepository
from ..security_events import NullSecurityEventSink, SecurityEventSink
from ..web_research.orchestrator import ResearchOrchestrator
from ..web_research.ports import ResearchRepositoryPort
from ..web_research.service import ResearchSubmissionService
from .errors import ApiError
from .routes.decisions import router
from .routes.intakes import router as intake_router
from .routes.pilot import router as pilot_router
from .routes.research import router as research_router

MAX_BODY_BYTES = 1_048_576


def create_app(
    repository: DecisionRepository,
    authenticator: Authenticator,
    intake_repository: IntakeRepository | None = None,
    policy_registry: PolicyRegistry | None = None,
    research_repository: ResearchRepositoryPort | None = None,
    research_orchestrator: ResearchOrchestrator | None = None,
    research_submission_service: ResearchSubmissionService | None = None,
    health_service: HealthService | None = None,
    logger: StructuredLoggerPort | None = None,
    metrics: MetricsPort | None = None,
    api_version: str = "0.4.0",
    build_metadata: BuildMetadata | None = None,
    security_events: SecurityEventSink | None = None,
    export_service: PilotExportService | None = None,
    lifecycle_service: PilotLifecycleService | None = None,
    queue_depth_probe: Callable[[], int] | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Decision Assurance API",
        version=api_version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.repository = repository
    app.state.authenticator = authenticator
    app.state.intake_repository = intake_repository
    app.state.policy_registry = policy_registry
    app.state.research_repository = research_repository
    app.state.research_orchestrator = research_orchestrator
    app.state.research_submission_service = research_submission_service
    app.state.security_events = security_events or NullSecurityEventSink()
    app.state.export_service = export_service
    app.state.lifecycle_service = lifecycle_service
    app.state.metrics = metrics
    app.state.assurance_outcomes = (
        AssuranceOutcomeCollector(metrics) if metrics is not None else None
    )

    @app.middleware("http")
    async def request_controls(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        request.state.correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_BODY_BYTES:
                    return _error_response(request, 413, "PAYLOAD_TOO_LARGE")
            except ValueError:
                return _error_response(request, 422, "INVALID_REQUEST")
        if request.method in {"POST", "PUT", "PATCH"} and content_length != "0":
            media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if media_type != "application/json" and not media_type.endswith("+json"):
                return _error_response(request, 415, "UNSUPPORTED_MEDIA_TYPE")
        if len(await request.body()) > MAX_BODY_BYTES:
            return _error_response(request, 413, "PAYLOAD_TOO_LARGE")
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = request.state.correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
        route = request.scope.get("route")
        route_name = getattr(route, "name", "unmatched")
        duration_ms = (time.perf_counter() - started) * 1000
        if logger is not None:
            logger.emit(
                "request.completed",
                level="INFO",
                correlation_id=request.state.correlation_id,
                fields={
                    "method": request.method,
                    "route": route_name,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 3),
                },
            )
        if metrics is not None:
            status_class = f"{response.status_code // 100}xx"
            metrics.increment(
                "http_requests_total", labels={"route": route_name, "status": status_class}
            )
            metrics.observe(
                "http_request_duration_seconds",
                duration_ms / 1000,
                labels={"route": route_name, "status": status_class},
            )
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, error: ApiError) -> JSONResponse:
        return _error_response(request, error.status_code, error.code, error.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        details = {
            "errors": [
                {"location": list(item["loc"]), "type": item["type"]} for item in error.errors()
            ]
        }
        return _error_response(request, 422, "INVALID_REQUEST", details)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
        del error
        return _error_response(request, 500, "INTERNAL_ERROR")

    @app.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok"}

    if metrics is not None:

        @app.get("/internal/metrics", include_in_schema=False)
        def internal_metrics() -> PlainTextResponse:
            if queue_depth_probe is not None:
                metrics.set_gauge("research_jobs_queued", queue_depth_probe())
            return PlainTextResponse(metrics.render_prometheus())

    if build_metadata is not None:

        @app.get("/version", tags=["health"])
        def version() -> dict[str, str]:
            return {
                "version": build_metadata.version,
                "commit_sha": build_metadata.commit_sha,
                "build_timestamp": build_metadata.build_timestamp,
                "database_schema_version": build_metadata.database_schema_version,
            }

    @app.get("/health/ready", tags=["health"])
    def ready() -> JSONResponse:
        if health_service is not None:
            report = health_service.check()
            return JSONResponse(
                {
                    "schema_version": report.schema_version,
                    "status": "ok" if report.ready else "unavailable",
                    "checked_at": report.checked_at,
                    "components": [
                        {
                            "component": item.component,
                            "status": item.status.value,
                            "reason_code": item.reason_code,
                            "critical": item.critical,
                        }
                        for item in report.components
                    ],
                },
                200 if report.ready else 503,
            )
        available = repository.ready()
        return JSONResponse(
            {"status": "ok" if available else "unavailable"}, 200 if available else 503
        )

    app.include_router(router)
    app.include_router(pilot_router)
    if intake_repository is not None and policy_registry is not None:
        app.include_router(intake_router)
    if research_repository is not None and research_orchestrator is not None:
        app.include_router(research_router)
    return app


def _error_response(
    request: Request, status: int, code: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    locale = select_locale(request.headers.get("Accept-Language"))
    return JSONResponse(
        {
            "code": code,
            "message": localize(code, locale),
            "correlation_id": request.state.correlation_id,
            "details": details or {},
        },
        status_code=status,
    )
