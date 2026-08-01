from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from psycopg import Error as PostgresError
from psycopg.types.json import Jsonb

from ..persistence.postgresql import PersistenceUnavailable, PostgresConnectionProvider
from ..tenancy import TenantContext
from .errors import BrowserOidcError
from .session import BrowserSession, SensitiveToken, _safe_identity


class PostgresSessionStore:
    def __init__(
        self,
        connections: PostgresConnectionProvider,
        *,
        session_pepper: bytes,
        envelope_key: bytes,
        ttl_seconds: int = 300,
        required_mfa_policy_version: str | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        if len(session_pepper) < 32 or not 30 <= ttl_seconds <= 1800:
            raise ValueError("INVALID_SHARED_SESSION_CONFIGURATION")
        try:
            self._fernet = Fernet(envelope_key)
        except (ValueError, TypeError):
            raise ValueError("INVALID_SESSION_ENVELOPE_KEY") from None
        self._connections = connections
        self._pepper = session_pepper
        self._ttl = ttl_seconds
        self._required_mfa_policy_version = required_mfa_policy_version
        self._clock = clock

    def ready(self) -> bool:
        try:
            with self._connections.worker_connection() as connection:
                row = connection.execute(
                    """
                    SELECT
                      to_regclass('decision_assurance_private.browser_sessions') IS NOT NULL AS session_table,
                      to_regprocedure('da_get_browser_session(text)') IS NOT NULL AS get_function,
                      to_regprocedure('da_revoke_browser_session(text)') IS NOT NULL AS revoke_function,
                      has_function_privilege(current_user, 'da_get_browser_session(text)', 'EXECUTE') AS can_get,
                      has_function_privilege(current_user, 'da_revoke_browser_session(text)', 'EXECUTE') AS can_revoke,
                      COALESCE((SELECT relrowsecurity AND relforcerowsecurity FROM pg_class
                        WHERE oid = 'decision_assurance_private.browser_sessions'::regclass), false) AS forced_rls
                    """
                ).fetchone()
                return row is not None and all(bool(value) for value in row.values())
        except (PostgresError, PersistenceUnavailable):
            return False

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
        session_id = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        expires = self._clock().astimezone(timezone.utc) + timedelta(
            seconds=min(self._ttl, token_expires_in)
        )
        encrypted = self._fernet.encrypt(access_token.value.encode()).decode("ascii")
        with self._connections.tenant_connection(
            TenantContext(str(safe_identity["tenant_id"]))
        ) as connection:
            connection.execute(
                "SELECT da_create_browser_session(%s,%s,%s,%s,%s,%s,%s)",
                (
                    self._digest(session_id),
                    safe_identity["tenant_id"],
                    safe_identity["actor_id"],
                    Jsonb(safe_identity),
                    csrf_token,
                    encrypted,
                    expires,
                ),
            )
        return BrowserSession(
            session_id, csrf_token, access_token, safe_identity, expires.timestamp()
        )

    def get(self, session_id: str | None) -> BrowserSession | None:
        if session_id is None or len(session_id) > 256:
            return None
        digest = self._digest(session_id)
        with self._connections.worker_connection() as connection:
            connection.execute(
                "SELECT set_config('decision_assurance.session_digest', %s, true)",
                (digest,),
            )
            row = connection.execute(
                "SELECT * FROM da_get_browser_session(%s)", (digest,)
            ).fetchone()
        if row is None:
            return None
        try:
            token = self._fernet.decrypt(str(row["token_ciphertext"]).encode()).decode()
            raw_identity = row["identity_json"]
            identity = json.loads(raw_identity) if isinstance(raw_identity, str) else raw_identity
            safe_identity = _safe_identity(identity)
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError, BrowserOidcError):
            raise BrowserOidcError("OIDC_SESSION_INVALID") from None
        expires = row["expires_at"]
        if not isinstance(expires, datetime) or expires <= self._clock().astimezone(timezone.utc):
            self.destroy(session_id)
            return None
        roles = safe_identity.get("roles")
        critical = {"SYSTEM_ADMINISTRATOR", "TENANT_ADMIN", "APPROVER", "AUDITOR"}
        if (
            self._required_mfa_policy_version is not None
            and isinstance(roles, list)
            and critical.intersection(str(role) for role in roles)
            and safe_identity.get("mfa_policy_version") != self._required_mfa_policy_version
        ):
            self.destroy(session_id)
            return None
        return BrowserSession(
            session_id,
            str(row["csrf_token"]),
            SensitiveToken(token),
            safe_identity,
            expires.timestamp(),
        )

    def destroy(self, session_id: str | None) -> None:
        if session_id is None or len(session_id) > 256:
            return
        digest = self._digest(session_id)
        with self._connections.worker_connection() as connection:
            connection.execute(
                "SELECT set_config('decision_assurance.session_digest', %s, true)",
                (digest,),
            )
            connection.execute("SELECT da_revoke_browser_session(%s)", (digest,))

    def revoke_actor(self, tenant_id: str, actor_id: str) -> None:
        with self._connections.tenant_connection(TenantContext(tenant_id)) as connection:
            connection.execute("SELECT da_revoke_actor_sessions(%s,%s)", (tenant_id, actor_id))

    def _digest(self, value: str) -> str:
        return "sha256:" + hmac.new(self._pepper, value.encode(), hashlib.sha256).hexdigest()
