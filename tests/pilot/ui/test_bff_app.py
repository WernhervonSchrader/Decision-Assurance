from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi.testclient import TestClient

from decision_assurance.oidc.mfa import MfaPolicy
from decision_assurance.pilot_ui.app import PilotUiSettings, create_pilot_ui_app
from decision_assurance.pilot_ui.oidc import TokenSet
from decision_assurance.pilot_ui.session import LoginTransaction, SensitiveToken


class FakeOidc:
    def authorization_url(self, transaction: LoginTransaction) -> str:
        return f"https://identity.example/auth?state={transaction.state}"

    def exchange(self, code: str, transaction: LoginTransaction) -> TokenSet:
        assert code == "valid-code"
        assert transaction.code_verifier
        return TokenSet(SensitiveToken("access-token-canary"), 300)


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def session(self, token: SensitiveToken, correlation_id: str) -> dict[str, object]:
        assert token.value == "access-token-canary"
        self.calls.append(("GET", "/v1/session", correlation_id))
        return {
            "actor_id": "alice",
            "tenant_id": "tenant-a",
            "actor_kind": "HUMAN",
            "roles": ["GENERATOR"],
        }

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
    ) -> httpx.Response:
        assert token.value == "access-token-canary"
        assert "tenant_id" not in query
        self.calls.append((method, path, correlation_id))
        return httpx.Response(
            200,
            json={"items": [{"decision_id": "quote-1", "status": "DRAFT"}]},
            headers={"content-type": "application/json"},
        )


def _app(api: FakeApi | None = None) -> TestClient:
    return TestClient(
        create_pilot_ui_app(
            PilotUiSettings(
                allowed_hosts=("pilot.example", "testserver"),
                trusted_proxy_cidrs=("172.30.0.0/24",),
                post_logout_redirect_uri="https://pilot.example/",
            ),
            FakeOidc(),
            api or FakeApi(),
        ),
        base_url="https://pilot.example",
    )


def _login(client: TestClient) -> tuple[dict[str, Any], str]:
    login = client.get("/auth/login?return_path=/cases", follow_redirects=False)
    state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]
    callback = client.get(f"/auth/callback?code=valid-code&state={state}", follow_redirects=False)
    assert callback.status_code == 303
    cookie = callback.headers["set-cookie"]
    assert "__Host-da_session=" in cookie
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert "Domain=" not in cookie and "Path=/" in cookie
    session = client.get("/bff/session")
    return session.json(), cookie


def test_login_rotates_to_secure_cookie_and_exposes_only_safe_identity() -> None:
    client = _app()

    session, cookie = _login(client)

    assert session["identity"]["tenant_id"] == "tenant-a"
    assert session["identity"]["actor_id"] == "alice"
    assert session["csrf_token"]
    surface = str(session) + cookie
    assert "access-token-canary" not in surface
    assert "refresh" not in surface.casefold()
    assert client.get("/bff/session").headers["strict-transport-security"]


def test_callback_is_bound_to_the_browser_that_started_login() -> None:
    application = create_pilot_ui_app(
        PilotUiSettings(
            allowed_hosts=("pilot.example",),
            trusted_proxy_cidrs=("172.30.0.0/24",),
            post_logout_redirect_uri="https://pilot.example/",
        ),
        FakeOidc(),
        FakeApi(),
    )
    attacker = TestClient(application, base_url="https://pilot.example")
    victim = TestClient(application, base_url="https://pilot.example")
    login = attacker.get("/auth/login", follow_redirects=False)
    state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]

    rejected = victim.get(f"/auth/callback?code=valid-code&state={state}", follow_redirects=False)

    assert rejected.status_code == 400
    assert victim.get("/bff/session").status_code == 401
    assert (
        attacker.get(
            f"/auth/callback?code=valid-code&state={state}", follow_redirects=False
        ).status_code
        == 303
    )


def test_critical_role_requires_validated_mfa_context() -> None:
    class ApproverApi(FakeApi):
        def session(self, token: SensitiveToken, correlation_id: str) -> dict[str, object]:
            identity = super().session(token, correlation_id)
            identity["roles"] = ["APPROVER"]
            return identity

    class MfaOidc(FakeOidc):
        def __init__(self, methods: list[str]):
            self._methods = methods

        def exchange(self, code: str, transaction: LoginTransaction) -> TokenSet:
            base = super().exchange(code, transaction)
            return TokenSet(
                base.access_token,
                base.expires_in,
                {
                    "acr": "urn:da:pilot:mfa",
                    "amr": self._methods,
                    "auth_time": int(datetime.now(timezone.utc).timestamp()),
                },
            )

    policy = MfaPolicy(
        "mfa-v1",
        frozenset({"APPROVER"}),
        frozenset({"urn:da:pilot:mfa"}),
        frozenset({"otp", "webauthn"}),
        timedelta(minutes=15),
    )

    def client(methods: list[str]) -> TestClient:
        return TestClient(
            create_pilot_ui_app(
                PilotUiSettings(
                    allowed_hosts=("pilot.example",),
                    trusted_proxy_cidrs=("172.30.0.0/24",),
                    post_logout_redirect_uri="https://pilot.example/",
                    mfa_policy=policy,
                ),
                MfaOidc(methods),
                ApproverApi(),
            ),
            base_url="https://pilot.example",
        )

    denied = client(["pwd"])
    login = denied.get("/auth/login", follow_redirects=False)
    state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]
    assert (
        denied.get(
            f"/auth/callback?code=valid-code&state={state}", follow_redirects=False
        ).status_code
        == 400
    )

    allowed = client(["pwd", "webauthn"])
    session, _ = _login(allowed)
    assert session["identity"]["acr"] == "urn:da:pilot:mfa"


def test_proxy_requires_session_csrf_and_allowlisted_path() -> None:
    api = FakeApi()
    client = _app(api)
    session, _ = _login(client)

    listed = client.get("/bff/api/v1/decisions?limit=25")
    denied_csrf = client.post(
        "/bff/api/v1/decisions/quote-1/evaluate",
        headers={"Idempotency-Key": "eval-1"},
        json={},
    )
    allowed = client.post(
        "/bff/api/v1/decisions/quote-1/evaluate",
        headers={
            "Idempotency-Key": "eval-1",
            "X-CSRF-Token": session["csrf_token"],
        },
        json={},
    )
    blocked_path = client.get("/bff/api/admin/users")

    assert listed.status_code == 200
    assert denied_csrf.status_code == 403
    assert allowed.status_code == 200
    assert blocked_path.status_code == 404
    assert (
        "POST",
        "/v1/decisions/quote-1/evaluate",
        allowed.headers["x-correlation-id"],
    ) in api.calls


def test_host_forwarded_spoof_and_tenant_query_are_rejected_before_api() -> None:
    api = FakeApi()
    client = _app(api)
    _login(client)

    bad_host = client.get("/bff/session", headers={"Host": "evil.example"})
    forwarded = client.get("/bff/session", headers={"X-Forwarded-Host": "evil.example"})
    tenant = client.get("/bff/api/v1/decisions?tenant_id=tenant-b")

    assert bad_host.status_code == 400
    assert forwarded.status_code == 400
    assert tenant.status_code == 422


def test_logout_requires_csrf_and_expires_session() -> None:
    client = _app()
    session, _ = _login(client)

    assert client.post("/auth/logout").status_code == 403
    logout = client.post("/auth/logout", headers={"X-CSRF-Token": session["csrf_token"]})

    assert logout.status_code == 204
    assert "Max-Age=0" in logout.headers["set-cookie"]
    assert client.get("/bff/session").status_code == 401
