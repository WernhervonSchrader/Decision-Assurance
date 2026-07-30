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
    OperatingMode,
    SecretProviderMode,
    SecretReference,
)

_EU_COUNTRY_CODES = frozenset(
    {
        "AT",
        "BE",
        "BG",
        "CY",
        "CZ",
        "DE",
        "DK",
        "EE",
        "ES",
        "FI",
        "FR",
        "GR",
        "HR",
        "HU",
        "IE",
        "IT",
        "LT",
        "LU",
        "LV",
        "MT",
        "NL",
        "PL",
        "PT",
        "RO",
        "SE",
        "SI",
        "SK",
    }
)
_RESIDENCY_FIELDS = frozenset(
    {
        "storage_locations",
        "processing_locations",
        "backup_locations",
        "support_access_locations",
        "external_processing_locations",
        "evidence_refs",
    }
)


@dataclass(frozen=True, slots=True)
class OidcRuntimeConfig:
    policy: OidcPolicy
    jwks_uri: str

    def __post_init__(self) -> None:
        if not self.jwks_uri.startswith("https://"):
            raise ValueError("INVALID_OIDC_JWKS_URI")


@dataclass(frozen=True, slots=True)
class DataResidencyPolicy:
    storage_locations: tuple[str, ...]
    processing_locations: tuple[str, ...]
    backup_locations: tuple[str, ...]
    support_access_locations: tuple[str, ...]
    external_processing_locations: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def validate_for(self, mode: OperatingMode) -> None:
        required = (
            self.storage_locations,
            self.processing_locations,
            self.backup_locations,
            self.support_access_locations,
        )
        if any(not locations for locations in required):
            raise ValueError("DATA_LOCATION_REQUIRED")
        if mode is OperatingMode.LOCAL:
            if any(locations != ("local",) for locations in required):
                raise ValueError("LOCAL_DATA_BOUNDARY_REQUIRED")
            return
        all_locations = (
            *self.storage_locations,
            *self.processing_locations,
            *self.backup_locations,
            *self.support_access_locations,
            *self.external_processing_locations,
        )
        if any(location not in _EU_COUNTRY_CODES for location in all_locations):
            raise ValueError("EU_DATA_LOCATION_REQUIRED")
        if not self.evidence_refs:
            raise ValueError("EU_RESIDENCY_EVIDENCE_REQUIRED")
        if any(not reference.startswith("https://") for reference in self.evidence_refs):
            raise ValueError("INVALID_RESIDENCY_EVIDENCE_REFERENCE")


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    profile: EnvironmentProfile
    operating_mode: OperatingMode | None
    data_residency: DataResidencyPolicy | None
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
            if self.operating_mode is None:
                raise ValueError("OPERATING_MODE_REQUIRED")
            if self.data_residency is None:
                raise ValueError("DATA_RESIDENCY_POLICY_REQUIRED")
            self.data_residency.validate_for(self.operating_mode)
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
        operating_mode_raw = raw.get("operating_mode")
        operating_mode = (
            OperatingMode(operating_mode_raw) if isinstance(operating_mode_raw, str) else None
        )
        residency_raw = raw.get("data_residency")
        residency = _residency_policy(residency_raw) if residency_raw is not None else None
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
            operating_mode=operating_mode,
            data_residency=residency,
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


def _residency_policy(raw: object) -> DataResidencyPolicy:
    if not isinstance(raw, Mapping):
        raise ValueError("INVALID_DATA_RESIDENCY_POLICY")
    unknown = set(raw).difference(_RESIDENCY_FIELDS)
    if unknown:
        raise ValueError("UNKNOWN_DATA_RESIDENCY_FIELD")
    return DataResidencyPolicy(
        storage_locations=_locations(raw, "storage_locations"),
        processing_locations=_locations(raw, "processing_locations"),
        backup_locations=_locations(raw, "backup_locations"),
        support_access_locations=_locations(raw, "support_access_locations"),
        external_processing_locations=_locations(raw, "external_processing_locations"),
        evidence_refs=_string_tuple(raw, "evidence_refs"),
    )


def _locations(raw: Mapping[str, Any], key: str) -> tuple[str, ...]:
    values = _string_tuple(raw, key)
    return tuple(value if value == "local" else value.upper() for value in values)


def _string_tuple(raw: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"INVALID_CONFIG_VALUE:{key}")
    normalized = tuple(item.strip() for item in value)
    if any(not item for item in normalized) or len(set(normalized)) != len(normalized):
        raise ValueError(f"INVALID_CONFIG_VALUE:{key}")
    return normalized


def _reject_literal_secrets(raw: Mapping[str, Any]) -> None:
    forbidden = {"password", "api_key", "token", "secret_value", "database_dsn"}
    for key, value in raw.items():
        if key.casefold() in forbidden:
            raise ValueError("LITERAL_SECRET_FORBIDDEN")
        if isinstance(value, Mapping):
            _reject_literal_secrets(value)
