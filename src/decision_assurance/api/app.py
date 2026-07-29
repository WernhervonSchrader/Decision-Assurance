from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..i18n import localize, select_locale
from ..repositories.protocols import DecisionRepository
from ..identity import Authenticator
from .errors import ApiError
from .routes.decisions import router


MAX_BODY_BYTES = 1_048_576


def create_app(repository: DecisionRepository, authenticator: Authenticator) -> FastAPI:
    app = FastAPI(title="Decision Assurance API", version="0.2.0")
    app.state.repository = repository
    app.state.authenticator = authenticator

    @app.middleware("http")
    async def request_controls(request: Request, call_next):
        request.state.correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_BYTES:
            return _error_response(request, 413, "PAYLOAD_TOO_LARGE")
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = request.state.correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, error: ApiError):
        return _error_response(request, error.status_code, error.code, error.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, error: RequestValidationError):
        details = {"errors": [{"location": list(item["loc"]), "type": item["type"]} for item in error.errors()]}
        return _error_response(request, 422, "INVALID_REQUEST", details)

    @app.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def ready() -> JSONResponse:
        available = repository.ready()  # type: ignore[attr-defined]
        return JSONResponse({"status": "ok" if available else "unavailable"}, 200 if available else 503)

    app.include_router(router)
    return app


def _error_response(
    request: Request, status: int, code: str, details: dict | None = None
) -> JSONResponse:
    locale = select_locale(request.headers.get("Accept-Language"))
    return JSONResponse(
        {"code": code, "message": localize(code, locale), "correlation_id": request.state.correlation_id, "details": details or {}},
        status_code=status,
    )
