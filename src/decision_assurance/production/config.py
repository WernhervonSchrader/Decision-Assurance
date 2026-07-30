from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import (
    AuthenticationMode,
    DatabaseBackend,
    EnvironmentProfile,
    JobPolicy,
    OidcPolicy,
    SecretProviderMode,
    SecretReference,
)


@dataclass(frozen=True, slots=True)
class OidcRuntimeConfig:
    policy: OidcPolicy
    jwks_uri: str

    def __post_init__(self) -> None:
        if not self.jwks_uri.startswith("https://"):
            raise ValueError("INVALID_OIDC_JWKS_URI")


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    profile: EnvironmentProfile
    database_backend: DatabaseBackend
    authentication_mode: AuthenticationMode
    secret_provider: SecretProviderMode
    database_dsn_secret: SecretReference
    worker_database_dsn_secret: SecretReference
    oidc: OidcRuntimeConfig | None
    egress_allowed_hosts: tuple[str, ...]
    worker_policy: JobPolicy

    def __post_init__(self) -> None:
        if self.profile in {EnvironmentProfile.STAGING, EnvironmentProfile.PRODUCTION}:
            if self.database_backend is not DatabaseBackend.POSTGRESQL:
                raise ValueError("PRODUCTION_REQUIRES_POSTGRESQL")
            if self.authentication_mode is not AuthenticationMode.OIDC or self.oidc is None:
                raise ValueError("PRODUCTION_REQUIRES_OIDC")
            if self.secret_provider is not SecretProviderMode.EXTERNAL:
                raise ValueError("EXTERNAL_SECRET_PROVIDER_REQUIRED")
            if not self.egress_allowed_hosts:
                raise ValueError("EGRESS_ALLOWLIST_REQUIRED")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> RuntimeConfig:
        _reject_literal_secrets(raw)
        profile = EnvironmentProfile(_required(raw, "profile"))
        backend = DatabaseBackend(_required(raw, "database_backend"))
        auth = AuthenticationMode(_required(raw, "authentication_mode"))
        oidc_raw = raw.get("oidc")
        oidc: OidcRuntimeConfig | None = None
        if oidc_raw is not None:
            if not isinstance(oidc_raw, Mapping):
                raise ValueError("INVALID_OIDC_CONFIGURATION")
            algorithms = oidc_raw.get("algorithms")
            if not isinstance(algorithms, list) or any(
                not isinstance(item, str) for item in algorithms
            ):
                raise ValueError("INVALID_OIDC_ALGORITHM_ALLOWLIST")
            oidc = OidcRuntimeConfig(
                OidcPolicy(
                    issuer=_required(oidc_raw, "issuer"),
                    audience=_required(oidc_raw, "audience"),
                    algorithms=tuple(algorithms),
                    tenant_claim=str(oidc_raw.get("tenant_claim", "tenant_id")),
                    actor_id_claim=str(oidc_raw.get("actor_id_claim", "sub")),
                    role_claim=str(oidc_raw.get("role_claim", "role")),
                    actor_kind_claim=str(oidc_raw.get("actor_kind_claim", "actor_kind")),
                    organization_claim=_optional(oidc_raw, "organization_claim"),
                    groups_claim=_optional(oidc_raw, "groups_claim"),
                    clock_skew_seconds=int(oidc_raw.get("clock_skew_seconds", 30)),
                ),
                _required(oidc_raw, "jwks_uri"),
            )
        worker = raw.get("worker", {})
        if not isinstance(worker, Mapping):
            raise ValueError("INVALID_WORKER_CONFIGURATION")
        hosts = raw.get("egress_allowed_hosts", [])
        if not isinstance(hosts, list) or any(not isinstance(item, str) for item in hosts):
            raise ValueError("INVALID_EGRESS_ALLOWLIST")
        return cls(
            profile=profile,
            database_backend=backend,
            authentication_mode=auth,
            secret_provider=SecretProviderMode(_required(raw, "secret_provider")),
            database_dsn_secret=SecretReference(_required(raw, "database_dsn_secret")),
            worker_database_dsn_secret=SecretReference(
                _required(raw, "worker_database_dsn_secret")
            ),
            oidc=oidc,
            egress_allowed_hosts=tuple(hosts),
            worker_policy=JobPolicy(
                max_attempts=int(worker.get("max_attempts", 5)),
                lease_seconds=int(worker.get("lease_seconds", 60)),
                base_backoff_seconds=int(worker.get("base_backoff_seconds", 5)),
                maximum_backoff_seconds=int(worker.get("maximum_backoff_seconds", 300)),
            ),
        )


def load_config(path: Path, environment: Mapping[str, str]) -> RuntimeConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ValueError("CONFIGURATION_UNAVAILABLE") from None
    if not isinstance(raw, dict):
        raise ValueError("INVALID_CONFIGURATION")
    overrides = {
        "DA_PROFILE": "profile",
        "DA_DATABASE_BACKEND": "database_backend",
        "DA_AUTHENTICATION_MODE": "authentication_mode",
        "DA_SECRET_PROVIDER": "secret_provider",
    }
    for environment_name, config_name in overrides.items():
        if environment_name in environment:
            raw[config_name] = environment[environment_name]
    return RuntimeConfig.from_mapping(raw)


def _required(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise ValueError(f"CONFIG_VALUE_REQUIRED:{key}")
    return value


def _optional(raw: Mapping[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"INVALID_CONFIG_VALUE:{key}")
    return value


def _reject_literal_secrets(raw: Mapping[str, Any]) -> None:
    forbidden = {"password", "api_key", "token", "secret_value", "database_dsn"}
    for key, value in raw.items():
        if key.casefold() in forbidden:
            raise ValueError("LITERAL_SECRET_FORBIDDEN")
        if isinstance(value, Mapping):
            _reject_literal_secrets(value)
