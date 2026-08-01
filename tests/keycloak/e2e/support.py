from __future__ import annotations

import base64
import hashlib
import html.parser
import os
import secrets
import shutil
import subprocess
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

KEYCLOAK_URL = "http://127.0.0.1:8080"
REALM = "decision-assurance"
REDIRECT_URI = "http://127.0.0.1:18080/callback"


def require_live_keycloak() -> None:
    if os.getenv("DA_RUN_KEYCLOAK_E2E") != "1":
        pytest.skip("Keycloak E2E requires explicit DA_RUN_KEYCLOAK_E2E=1 opt-in")


def _secret(name: str) -> str:
    value = (Path(".secrets") / name).read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError("KEYCLOAK_E2E_SECRET_UNAVAILABLE")
    return value


def _admin_token() -> str:
    response = httpx.post(
        f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": _secret("keycloak-admin-username"),
            "password": _secret("keycloak-admin-password"),
        },
        timeout=10.0,
    )
    if response.status_code != 200:
        raise RuntimeError(f"KEYCLOAK_ADMIN_AUTH_FAILED:{response.status_code // 100}xx")
    token = response.json().get("access_token")
    if not isinstance(token, str):
        raise RuntimeError("KEYCLOAK_ADMIN_TOKEN_INVALID")
    return token


def _admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_admin_token()}"}


def required_action_providers() -> dict[str, bool]:
    response = httpx.get(
        f"{KEYCLOAK_URL}/admin/realms/{REALM}/authentication/required-actions",
        headers=_admin_headers(),
        timeout=10.0,
    )
    if response.status_code != 200:
        raise RuntimeError(f"KEYCLOAK_REQUIRED_ACTIONS_FAILED:{response.status_code // 100}xx")
    return {
        str(item["providerId"]): bool(item["enabled"])
        for item in response.json()
        if isinstance(item, dict) and "providerId" in item
    }


@dataclass(frozen=True, slots=True)
class TemporaryUser:
    user_id: str
    username: str
    password: str = field(repr=False)
    tenant_id: str
    roles: tuple[str, ...]


@contextmanager
def temporary_user(*, tenant_id: str, roles: Sequence[str]) -> Iterator[TemporaryUser]:
    suffix = secrets.token_hex(8)
    username = f"e2e-{suffix}"
    password = secrets.token_urlsafe(32)
    headers = _admin_headers()
    response = httpx.post(
        f"{KEYCLOAK_URL}/admin/realms/{REALM}/users",
        headers=headers,
        json={
            "username": username,
            "enabled": True,
            "emailVerified": True,
            "firstName": "Isolated",
            "lastName": "E2E",
            "email": f"{username}@example.invalid",
            "attributes": {
                "tenant_id": [tenant_id],
                "actor_kind": ["HUMAN"],
                "organization": [f"org-{tenant_id}"],
            },
            "credentials": [{"type": "password", "value": password, "temporary": False}],
        },
        timeout=10.0,
    )
    if response.status_code != 201:
        raise RuntimeError(f"KEYCLOAK_USER_CREATE_FAILED:{response.status_code // 100}xx")
    user_id = response.headers["Location"].rstrip("/").rsplit("/", 1)[-1]
    try:
        representations: list[dict[str, object]] = []
        for role in roles:
            role_response = httpx.get(
                f"{KEYCLOAK_URL}/admin/realms/{REALM}/roles/{role}",
                headers=headers,
                timeout=10.0,
            )
            if role_response.status_code != 200:
                raise RuntimeError(
                    f"KEYCLOAK_ROLE_LOOKUP_FAILED:{role_response.status_code // 100}xx"
                )
            representations.append(role_response.json())
        assignment = httpx.post(
            f"{KEYCLOAK_URL}/admin/realms/{REALM}/users/{user_id}/role-mappings/realm",
            headers=headers,
            json=representations,
            timeout=10.0,
        )
        if assignment.status_code != 204:
            raise RuntimeError(f"KEYCLOAK_ROLE_ASSIGNMENT_FAILED:{assignment.status_code // 100}xx")
        yield TemporaryUser(user_id, username, password, tenant_id, tuple(roles))
    finally:
        httpx.delete(
            f"{KEYCLOAK_URL}/admin/realms/{REALM}/users/{user_id}",
            headers=_admin_headers(),
            timeout=10.0,
        )


class _LoginForm(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.action: str | None = None
        self.hidden: dict[str, str] = {}
        self._inside = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "form" and values.get("id") == "kc-form-login":
            self._inside = True
            self.action = values.get("action")
        elif self._inside and tag == "input" and values.get("type") == "hidden":
            name = values.get("name")
            if name:
                self.hidden[name] = values.get("value") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._inside:
            self._inside = False


def pkce_access_token(user: TemporaryUser) -> str:
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    with httpx.Client(follow_redirects=False, timeout=10.0) as client:
        login = client.get(
            f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/auth",
            params={
                "client_id": "decision-assurance-e2e",
                "redirect_uri": REDIRECT_URI,
                "response_type": "code",
                "scope": "openid da.api",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": state,
                "nonce": nonce,
            },
        )
        if login.status_code != 200:
            raise RuntimeError(f"KEYCLOAK_AUTHORIZE_FAILED:{login.status_code // 100}xx")
        parser = _LoginForm()
        parser.feed(login.text)
        if parser.action is None:
            raise RuntimeError("KEYCLOAK_LOGIN_FORM_INVALID")
        # Keycloak deliberately marks auth-session cookies Secure. Browsers treat loopback
        # as a trustworthy local context; httpx applies the generic HTTP cookie rule.
        # Emulate only that browser exception inside the isolated loopback E2E harness.
        for cookie in client.cookies.jar:
            if cookie.domain in {"127.0.0.1", "localhost"}:
                cookie.secure = False
        form = dict(parser.hidden)
        form.update({"username": user.username, "password": user.password, "credentialId": ""})
        authenticated = client.post(parser.action, data=form)
        if authenticated.status_code not in {302, 303}:
            raise RuntimeError(f"KEYCLOAK_LOGIN_FAILED:{authenticated.status_code // 100}xx")
        location = authenticated.headers.get("Location", "")
        query = parse_qs(urlparse(location).query)
        if query.get("state") != [state] or not query.get("code"):
            raise RuntimeError("KEYCLOAK_AUTHORIZATION_RESPONSE_INVALID")
        token_response = client.post(
            f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
            data={
                "grant_type": "authorization_code",
                "client_id": "decision-assurance-e2e",
                "redirect_uri": REDIRECT_URI,
                "code": query["code"][0],
                "code_verifier": verifier,
            },
        )
    if token_response.status_code != 200:
        raise RuntimeError(f"KEYCLOAK_CODE_EXCHANGE_FAILED:{token_response.status_code // 100}xx")
    token = token_response.json().get("access_token")
    if not isinstance(token, str):
        raise RuntimeError("KEYCLOAK_ACCESS_TOKEN_INVALID")
    return token


def restart_keycloak() -> None:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("KEYCLOAK_DOCKER_UNAVAILABLE")
    project = os.getenv("DA_KEYCLOAK_COMPOSE_PROJECT", "decision-assurance-keycloak-local")
    completed = subprocess.run(  # noqa: S603 - fixed argv and resolved Docker executable
        [
            docker,
            "compose",
            "-p",
            project,
            "-f",
            "compose.keycloak.yaml",
            "restart",
            "keycloak",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if completed.returncode != 0:
        raise RuntimeError("KEYCLOAK_RESTART_FAILED")
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            if httpx.get("http://127.0.0.1:9000/health/ready", timeout=2.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError("KEYCLOAK_RESTART_READINESS_TIMEOUT")
