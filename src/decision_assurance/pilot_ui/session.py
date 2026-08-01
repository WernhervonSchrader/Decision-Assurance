from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from .errors import BrowserOidcError


@dataclass(frozen=True, slots=True, repr=False)
class SensitiveToken:
    value: str

    def __post_init__(self) -> None:
        if not self.value or len(self.value) > 16_384:
            raise BrowserOidcError("OIDC_TOKEN_INVALID")

    def __repr__(self) -> str:
        return "SensitiveToken(**redacted**)"


@dataclass(frozen=True, slots=True, repr=False)
class LoginTransaction:
    state: str
    nonce: str
    code_verifier: str
    return_path: str
    expires_at: float
    browser_binding_hash: str = ""

    def __repr__(self) -> str:
        return "LoginTransaction(**redacted**)"


class LoginTransactionStore:
    def __init__(
        self,
        *,
        ttl_seconds: int = 180,
        capacity: int = 256,
        allowed_return_paths: tuple[str, ...] = ("/", "/cases"),
        clock: Callable[[], float] = time.monotonic,
    ):
        if not 30 <= ttl_seconds <= 600 or not 1 <= capacity <= 10_000:
            raise ValueError("INVALID_LOGIN_TRANSACTION_LIMIT")
        self._ttl = ttl_seconds
        self._capacity = capacity
        self._allowed_return_paths = frozenset(allowed_return_paths)
        self._clock = clock
        self._values: dict[str, LoginTransaction] = {}
        self._lock = threading.Lock()

    def create(self, return_path: str, browser_binding: str) -> LoginTransaction:
        if return_path not in self._allowed_return_paths:
            raise BrowserOidcError("OIDC_RETURN_PATH_INVALID")
        binding_hash = _browser_binding_hash(browser_binding)
        with self._lock:
            self._prune()
            if len(self._values) >= self._capacity:
                raise BrowserOidcError("OIDC_LOGIN_CAPACITY_EXCEEDED")
            transaction = LoginTransaction(
                state=secrets.token_urlsafe(32),
                nonce=secrets.token_urlsafe(32),
                code_verifier=secrets.token_urlsafe(64),
                return_path=return_path,
                expires_at=self._clock() + self._ttl,
                browser_binding_hash=binding_hash,
            )
            self._values[transaction.state] = transaction
            return transaction

    def consume(self, state: str, browser_binding: str) -> LoginTransaction:
        if not state or len(state) > 256:
            raise BrowserOidcError("OIDC_STATE_INVALID")
        binding_hash = _browser_binding_hash(browser_binding)
        with self._lock:
            self._prune()
            transaction = self._values.get(state)
            if transaction is not None and hmac.compare_digest(
                transaction.browser_binding_hash, binding_hash
            ):
                self._values.pop(state, None)
            else:
                transaction = None
        if transaction is None or transaction.expires_at <= self._clock():
            raise BrowserOidcError("OIDC_STATE_INVALID")
        return transaction

    def _prune(self) -> None:
        now = self._clock()
        expired = [key for key, value in self._values.items() if value.expires_at <= now]
        for key in expired:
            self._values.pop(key, None)


def _browser_binding_hash(value: str) -> str:
    if not value or len(value) > 256:
        raise BrowserOidcError("OIDC_BROWSER_BINDING_INVALID")
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class BrowserSession:
    session_id: str
    csrf_token: str
    access_token: SensitiveToken
    identity: Mapping[str, object]
    expires_at: float

    def __repr__(self) -> str:
        return "BrowserSession(**redacted**)"


class BrowserSessionStore(Protocol):
    def create(
        self,
        access_token: SensitiveToken,
        identity: Mapping[str, object],
        *,
        token_expires_in: int,
    ) -> BrowserSession: ...

    def get(self, session_id: str | None) -> BrowserSession | None: ...

    def destroy(self, session_id: str | None) -> None: ...


class SessionStore:
    def __init__(
        self,
        *,
        ttl_seconds: int = 300,
        capacity: int = 1_000,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not 30 <= ttl_seconds <= 1800 or not 1 <= capacity <= 100_000:
            raise ValueError("INVALID_SESSION_LIMIT")
        self._ttl = ttl_seconds
        self._capacity = capacity
        self._clock = clock
        self._values: dict[str, BrowserSession] = {}
        self._lock = threading.Lock()

    def create(
        self,
        access_token: SensitiveToken,
        identity: Mapping[str, object],
        *,
        token_expires_in: int,
    ) -> BrowserSession:
        if token_expires_in <= 0:
            raise BrowserOidcError("OIDC_TOKEN_EXPIRED")
        safe_identity = _safe_identity(identity)
        with self._lock:
            self._prune()
            if len(self._values) >= self._capacity:
                raise BrowserOidcError("OIDC_SESSION_CAPACITY_EXCEEDED")
            session = BrowserSession(
                session_id=secrets.token_urlsafe(32),
                csrf_token=secrets.token_urlsafe(32),
                access_token=access_token,
                identity=safe_identity,
                expires_at=self._clock() + min(self._ttl, token_expires_in),
            )
            self._values[session.session_id] = session
            return session

    def get(self, session_id: str | None) -> BrowserSession | None:
        if session_id is None or len(session_id) > 256:
            return None
        with self._lock:
            self._prune()
            return self._values.get(session_id)

    def destroy(self, session_id: str | None) -> None:
        if session_id is None:
            return
        with self._lock:
            self._values.pop(session_id, None)

    def _prune(self) -> None:
        now = self._clock()
        expired = [key for key, value in self._values.items() if value.expires_at <= now]
        for key in expired:
            self._values.pop(key, None)


def _safe_identity(identity: Mapping[str, object]) -> dict[str, object]:
    required = {"actor_id", "tenant_id", "actor_kind", "roles"}
    optional = {"acr", "amr", "authenticated_at", "mfa_policy_version"}
    if not required.issubset(identity) or set(identity).difference(required | optional):
        raise BrowserOidcError("OIDC_IDENTITY_INVALID")
    actor_id = identity.get("actor_id")
    tenant_id = identity.get("tenant_id")
    actor_kind = identity.get("actor_kind")
    roles = identity.get("roles")
    if (
        not isinstance(actor_id, str)
        or not actor_id
        or not isinstance(tenant_id, str)
        or not tenant_id
        or actor_kind not in {"HUMAN", "AGENT", "SERVICE"}
        or not isinstance(roles, list)
        or not roles
        or any(not isinstance(role, str) or not role for role in roles)
    ):
        raise BrowserOidcError("OIDC_IDENTITY_INVALID")
    safe: dict[str, object] = {
        "actor_id": actor_id,
        "tenant_id": tenant_id,
        "actor_kind": actor_kind,
        "roles": list(roles),
    }
    if optional.intersection(identity):
        acr = identity.get("acr")
        amr = identity.get("amr")
        authenticated_at = identity.get("authenticated_at")
        policy_version = identity.get("mfa_policy_version")
        if (
            not isinstance(acr, str)
            or not acr
            or not isinstance(amr, list)
            or not amr
            or any(not isinstance(item, str) or not item for item in amr)
            or not isinstance(authenticated_at, str)
            or not authenticated_at
            or not isinstance(policy_version, str)
            or not policy_version
        ):
            raise BrowserOidcError("OIDC_IDENTITY_INVALID")
        safe.update(
            {
                "acr": acr,
                "amr": list(amr),
                "authenticated_at": authenticated_at,
                "mfa_policy_version": policy_version,
            }
        )
    return safe
