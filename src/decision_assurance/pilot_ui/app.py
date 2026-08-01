from __future__ import annotations

import hmac
import ipaddress
import json
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response as StarletteResponse

from ..production.ports import MetricsPort
from .api_client import PilotApiError
from .errors import BrowserOidcError
from .oidc import TokenSet
from .session import (
    BrowserSession,
    LoginTransaction,
    LoginTransactionStore,
    SensitiveToken,
    SessionStore,
)

SESSION_COOKIE = "__Host-da_session"
MAX_BODY_BYTES = 1_048_576
_CORRELATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PATHS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GET", re.compile(r"^/v1/session$")),
    ("GET", re.compile(r"^/v1/decisions$")),
    ("POST", re.compile(r"^/v1/intakes$")),
    ("GET", re.compile(r"^/v1/intakes/[A-Za-z0-9._:-]+$")),
    ("POST", re.compile(r"^/v1/intakes/[A-Za-z0-9._:-]+/(confirmations|compile)$")),
    ("POST", re.compile(r"^/v1/research-runs$")),
    ("GET", re.compile(r"^/v1/research-runs/[A-Za-z0-9._:-]+(/audit|/sources|/evidence)?$")),
    ("POST", re.compile(r"^/v1/research-runs/[A-Za-z0-9._:-]+/(retry|cancel|handoff)$")),
    ("GET", re.compile(r"^/v1/decisions/[A-Za-z0-9._:-]+(/report|/audit|/export)?$")),
    (
        "POST",
        re.compile(r"^/v1/decisions/[A-Za-z0-9._:-]+/(evaluate|transitions|deletion-requests)$"),
    ),
    ("PUT", re.compile(r"^/v1/decisions/[A-Za-z0-9._:-]+/legal-hold$")),
    ("DELETE", re.compile(r"^/v1/decisions/[A-Za-z0-9._:-]+/legal-hold$")),
    ("POST", re.compile(r"^/v1/deletion-requests/[A-Za-z0-9._:-]+/execute$")),
)


class BrowserOidcPort(Protocol):
    def authorization_url(self, transaction: LoginTransaction) -> str: ...
    def exchange(self, code: str, transaction: LoginTransaction) -> TokenSet: ...


class PilotApiPort(Protocol):
    def session(self, token: SensitiveToken, correlation_id: str) -> dict[str, object]: ...
    def request(
        self,
        token: SensitiveToken,
        method: str,
        path: str,
        *,
        query: str,
        body: bytes,
        locale: str,
        correlation_id: str,
        idempotency_key: str | None,
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class PilotUiSettings:
    allowed_hosts: tuple[str, ...]
    trusted_proxy_cidrs: tuple[str, ...]
    post_logout_redirect_uri: str
    session_ttl_seconds: int = 300
    session_capacity: int = 1_000
    asset_directory: Path | None = None
    oidc_end_session_endpoint: str | None = None
    oidc_client_id: str = "decision-assurance-pilot-ui"

    def __post_init__(self) -> None:
        if not self.allowed_hosts or not self.trusted_proxy_cidrs:
            raise ValueError("INCOMPLETE_PILOT_UI_SETTINGS")
        try:
            for value in self.trusted_proxy_cidrs:
                ipaddress.ip_network(value, strict=True)
        except ValueError:
            raise ValueError("INVALID_PILOT_PROXY_NETWORK") from None
        logout = urlsplit(self.post_logout_redirect_uri)
        if (
            logout.scheme != "https"
            or logout.hostname is None
            or logout.hostname.casefold().rstrip(".") not in self.allowed_hosts
        ):
            raise ValueError("INVALID_PILOT_LOGOUT_REDIRECT")
        if self.oidc_end_session_endpoint is not None:
            end_session = urlsplit(self.oidc_end_session_endpoint)
            if end_session.scheme != "https" or end_session.hostname is None:
                raise ValueError("INVALID_PILOT_END_SESSION_ENDPOINT")


def create_pilot_ui_app(
    settings: PilotUiSettings,
    oidc: BrowserOidcPort,
    api: PilotApiPort,
    *,
    login_store: LoginTransactionStore | None = None,
    session_store: SessionStore | None = None,
    metrics: MetricsPort | None = None,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    logins = login_store or LoginTransactionStore()
    sessions = session_store or SessionStore(
        ttl_seconds=settings.session_ttl_seconds, capacity=settings.session_capacity
    )
    allowed_hosts = frozenset(host.casefold().rstrip(".") for host in settings.allowed_hosts)
    trusted_networks = tuple(ipaddress.ip_network(value) for value in settings.trusted_proxy_cidrs)

    @app.middleware("http")
    async def security_boundary(
        request: Request, call_next: Callable[[Request], Awaitable[StarletteResponse]]
    ) -> StarletteResponse:
        correlation = request.headers.get("X-Correlation-ID", "")
        request.state.correlation_id = (
            correlation if _CORRELATION.fullmatch(correlation) else str(uuid.uuid4())
        )
        host = (request.url.hostname or "").casefold().rstrip(".")
        if host not in allowed_hosts:
            response: StarletteResponse = _error(400, "HOST_REJECTED", request)
        elif _untrusted_forwarded(request, trusted_networks):
            response = _error(400, "FORWARDED_HEADER_REJECTED", request)
        else:
            content_length = request.headers.get("content-length")
            try:
                too_large = content_length is not None and int(content_length) > MAX_BODY_BYTES
            except ValueError:
                too_large = True
            if too_large or len(await request.body()) > MAX_BODY_BYTES:
                response = _error(413, "PAYLOAD_TOO_LARGE", request)
            else:
                response = await call_next(request)
        _security_headers(response, request.state.correlation_id)
        return response

    @app.exception_handler(BrowserOidcError)
    async def oidc_error(request: Request, error: BrowserOidcError) -> JSONResponse:
        del error
        if metrics is not None:
            metrics.increment("pilot_login_total", labels={"status": "rejected"})
        return _error(400, "AUTHENTICATION_FAILED", request)

    @app.exception_handler(PilotApiError)
    async def api_error(request: Request, error: PilotApiError) -> JSONResponse:
        del error
        return _error(503, "PILOT_API_UNAVAILABLE", request)

    @app.exception_handler(_HttpError)
    async def http_error(request: Request, error: _HttpError) -> JSONResponse:
        return _error(error.status_code, error.code, request)

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready() -> dict[str, str]:
        return {"status": "ok"}

    if metrics is not None:

        @app.get("/internal/metrics", include_in_schema=False)
        def internal_metrics() -> PlainTextResponse:
            return PlainTextResponse(metrics.render_prometheus())

    @app.get("/auth/login")
    def login(request: Request, return_path: str = "/") -> RedirectResponse:
        del request
        transaction = logins.create(return_path)
        return RedirectResponse(oidc.authorization_url(transaction), status_code=303)

    @app.get("/auth/callback")
    def callback(request: Request, code: str, state: str) -> RedirectResponse:
        transaction = logins.consume(state)
        tokens = oidc.exchange(code, transaction)
        identity = api.session(tokens.access_token, request.state.correlation_id)
        session = sessions.create(tokens.access_token, identity, token_expires_in=tokens.expires_in)
        if metrics is not None:
            metrics.increment("pilot_login_total", labels={"status": "success"})
            metrics.increment("pilot_session_total", labels={"status": "created"})
        response = RedirectResponse(transaction.return_path, status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            session.session_id,
            max_age=min(settings.session_ttl_seconds, tokens.expires_in),
            secure=True,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return response

    @app.post("/auth/logout", status_code=204)
    def logout(request: Request) -> Response:
        session = _require_session(request, sessions)
        _require_csrf(request, session)
        sessions.destroy(session.session_id)
        if metrics is not None:
            metrics.increment("pilot_session_total", labels={"status": "destroyed"})
        response = Response(status_code=204)
        response.delete_cookie(SESSION_COOKIE, secure=True, httponly=True, samesite="lax", path="/")
        return response

    @app.get("/auth/end-session")
    def end_session() -> RedirectResponse:
        if settings.oidc_end_session_endpoint is None:
            return RedirectResponse(settings.post_logout_redirect_uri, status_code=303)
        query = urlencode(
            {
                "client_id": settings.oidc_client_id,
                "post_logout_redirect_uri": settings.post_logout_redirect_uri,
            }
        )
        return RedirectResponse(f"{settings.oidc_end_session_endpoint}?{query}", status_code=303)

    @app.get("/bff/session")
    def bff_session(request: Request) -> dict[str, object]:
        session = _require_session(request, sessions)
        return {"identity": dict(session.identity), "csrf_token": session.csrf_token}

    @app.api_route("/bff/api/{api_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def proxy(request: Request, api_path: str) -> Response:
        session = _require_session(request, sessions)
        path = "/" + api_path
        if not _allowed_path(request.method, path):
            return _error(404, "NOT_FOUND", request)
        query = request.url.query
        query_keys = {key for key in parse_qs(query, keep_blank_values=True)}
        if query_keys.intersection({"tenant", "tenant_id", "actor", "actor_id"}):
            return _error(422, "IDENTITY_OVERRIDE_REJECTED", request)
        body = await request.body()
        if request.method not in {"GET", "HEAD"}:
            _require_csrf(request, session)
            if body and _has_identity_override(body):
                return _error(422, "IDENTITY_OVERRIDE_REJECTED", request)
        upstream = api.request(
            session.access_token,
            request.method,
            path,
            query=query,
            body=body,
            locale=request.headers.get("Accept-Language", "en"),
            correlation_id=request.state.correlation_id,
            idempotency_key=request.headers.get("Idempotency-Key"),
        )
        headers = {
            name: upstream.headers[name]
            for name in ("content-type", "content-disposition")
            if name in upstream.headers
        }
        return Response(content=upstream.content, status_code=upstream.status_code, headers=headers)

    @app.get("/", response_class=HTMLResponse)
    @app.get("/cases", response_class=HTMLResponse)
    def shell() -> str:
        return _shell_html()

    if settings.asset_directory is not None:
        if not settings.asset_directory.is_dir():
            raise ValueError("PILOT_UI_ASSETS_UNAVAILABLE")
        app.mount("/assets", StaticFiles(directory=settings.asset_directory), name="assets")

    return app


def _require_session(request: Request, sessions: SessionStore) -> BrowserSession:
    session = sessions.get(request.cookies.get(SESSION_COOKIE))
    if session is None:
        raise _HttpError(401, "AUTHENTICATION_REQUIRED")
    return session


def _require_csrf(request: Request, session: BrowserSession) -> None:
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied or not hmac.compare_digest(supplied, session.csrf_token):
        raise _HttpError(403, "CSRF_REJECTED")


class _HttpError(Exception):
    def __init__(self, status_code: int, code: str):
        self.status_code = status_code
        self.code = code


def _error(status: int, code: str, request: Request) -> JSONResponse:
    return JSONResponse(
        {"code": code, "correlation_id": request.state.correlation_id}, status_code=status
    )


def _security_headers(response: StarletteResponse, correlation_id: str) -> None:
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"


def _untrusted_forwarded(
    request: Request, trusted_networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]
) -> bool:
    if not any(
        name in request.headers for name in ("forwarded", "x-forwarded-host", "x-forwarded-proto")
    ):
        return False
    client = request.client
    if client is None:
        return True
    try:
        address = ipaddress.ip_address(client.host)
    except ValueError:
        return True
    return not any(address in network for network in trusted_networks)


def _allowed_path(method: str, path: str) -> bool:
    return any(
        allowed_method == method and pattern.fullmatch(path) for allowed_method, pattern in _PATHS
    )


def _has_identity_override(body: bytes) -> bool:
    try:
        value = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False

    def inspect(item: object) -> bool:
        if isinstance(item, dict):
            if set(item).intersection({"tenant", "tenant_id", "actor_id"}):
                return True
            return any(inspect(child) for child in item.values())
        if isinstance(item, list):
            return any(inspect(child) for child in item)
        return False

    return inspect(value)


def _shell_html() -> str:
    return """<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Decision Assurance Pilot</title><link rel=\"stylesheet\" href=\"/assets/style.css\"></head><body><main id=\"app\"><h1>Decision Assurance Pilot</h1><p>Loading controlled pilot…</p></main><script type=\"module\" src=\"/assets/app.js\"></script></body></html>"""
