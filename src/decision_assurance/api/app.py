from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response

from ..i18n import localize, select_locale
from ..identity import Authenticator
from ..intake.repository import IntakeRepository
from ..intake.verification import PolicyRegistry
from ..repositories.protocols import DecisionRepository
from ..web_research.orchestrator import ResearchOrchestrator
from ..web_research.repository import SqliteResearchRepository
from ..web_research.service import ResearchSubmissionService
from .errors import ApiError
from .routes.decisions import router
from .routes.intakes import router as intake_router
from .routes.research import router as research_router

MAX_BODY_BYTES = 1_048_576


def create_app(
    repository: DecisionRepository,
    authenticator: Authenticator,
    intake_repository: IntakeRepository | None = None,
    policy_registry: PolicyRegistry | None = None,
    research_repository: SqliteResearchRepository | None = None,
    research_orchestrator: ResearchOrchestrator | None = None,
    research_submission_service: ResearchSubmissionService | None = None,
) -> FastAPI:
    app = FastAPI(title="Decision Assurance API", version="0.4.0")
    app.state.repository = repository
    app.state.authenticator = authenticator
    app.state.intake_repository = intake_repository
    app.state.policy_registry = policy_registry
    app.state.research_repository = research_repository
    app.state.research_orchestrator = research_orchestrator
    app.state.research_submission_service = research_submission_service

    @app.middleware("http")
    async def request_controls(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
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

    @app.get("/health/ready", tags=["health"])
    def ready() -> JSONResponse:
        available = repository.ready()
        return JSONResponse(
            {"status": "ok" if available else "unavailable"}, 200 if available else 503
        )

    app.include_router(router)
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
