from __future__ import annotations

import ipaddress
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..provenance.config import SigningSettings
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
_PROVIDER_EGRESS_FIELDS = frozenset(
    {
        "provider",
        "service",
        "host",
        "processing_location",
        "confirmed_processing_locations",
        "tenant_ids",
        "attestation",
    }
)
_ATTESTATION_FIELDS = frozenset(
    {
        "evidence_id",
        "evidence_type",
        "evidence_ref",
        "issuer",
        "issued_at",
        "valid_from",
        "expires_at",
        "verification_status",
        "verified_at",
        "verified_by",
        "document_hash",
    }
)
_EVIDENCE_TYPES = frozenset(
    {
        "DPA",
        "SIGNED_PROVIDER_ATTESTATION",
        "TECHNICAL_PROVIDER_CONFIGURATION",
        "OPERATOR_SELF_DECLARATION",
    }
)
_VERIFICATION_STATUSES = frozenset({"VERIFIED", "UNVERIFIED", "EXPIRED", "REVOKED"})
_CONTROLLED_PILOT_FIELDS = frozenset(
    {
        "public_base_url",
        "oidc_redirect_uri",
        "post_logout_redirect_uri",
        "allowed_hosts",
        "trusted_proxy_cidrs",
        "audit_persistence",
        "backup_configuration_ref",
        "lifecycle_pseudonymization_secret",
        "session_pepper_secret",
        "session_envelope_key_secret",
        "export_signing",
        "retention_days",
        "pilot_tenant",
        "health_path",
        "readiness_path",
    }
)


@dataclass(frozen=True, slots=True)
class ControlledPilotConfig:
    public_base_url: str
    oidc_redirect_uri: str
    post_logout_redirect_uri: str
    allowed_hosts: tuple[str, ...]
    trusted_proxy_cidrs: tuple[str, ...]
    audit_persistence: bool
    backup_configuration_ref: str
    lifecycle_pseudonymization_secret: SecretReference
    session_pepper_secret: SecretReference
    session_envelope_key_secret: SecretReference
    export_signing: SigningSettings
    retention_days: int
    pilot_tenant: str
    health_path: str
    readiness_path: str

    def __post_init__(self) -> None:
        urls = (self.public_base_url, self.oidc_redirect_uri, self.post_logout_redirect_uri)
        parsed = tuple(urlsplit(value) for value in urls)
        if any(item.scheme != "https" or not item.hostname for item in parsed):
            raise ValueError("PILOT_HTTPS_REQUIRED")
        if any(item.hostname in {"localhost", "127.0.0.1", "::1"} for item in parsed):
            raise ValueError("PILOT_LOOPBACK_FORBIDDEN")
        if any(item.username or item.password or item.fragment for item in parsed):
            raise ValueError("INVALID_PILOT_PUBLIC_URL")
        normalized_hosts = tuple(item.casefold().rstrip(".") for item in self.allowed_hosts)
        if not normalized_hosts or any(not item for item in normalized_hosts):
            raise ValueError("PILOT_ALLOWED_HOSTS_REQUIRED")
        public_host = parsed[0].hostname
        if public_host is None or public_host.casefold().rstrip(".") not in normalized_hosts:
            raise ValueError("PILOT_PUBLIC_HOST_NOT_ALLOWED")
        if any(item.hostname != public_host for item in parsed[1:]):
            raise ValueError("PILOT_REDIRECT_HOST_MISMATCH")
        object.__setattr__(self, "allowed_hosts", normalized_hosts)
        if not self.trusted_proxy_cidrs:
            raise ValueError("PILOT_TRUSTED_PROXY_REQUIRED")
        try:
            for network in self.trusted_proxy_cidrs:
                ipaddress.ip_network(network, strict=True)
        except ValueError:
            raise ValueError("INVALID_PILOT_TRUSTED_PROXY") from None
        if not self.audit_persistence:
            raise ValueError("PILOT_AUDIT_PERSISTENCE_REQUIRED")
        backup = self.backup_configuration_ref.strip().casefold()
        if not backup or backup in {"example", "default", "placeholder", "changeme"}:
            raise ValueError("PILOT_BACKUP_CONFIGURATION_REQUIRED")
        if not 1 <= self.retention_days <= 3650:
            raise ValueError("PILOT_RETENTION_REQUIRED")
        if not self.pilot_tenant.strip():
            raise ValueError("PILOT_TENANT_REQUIRED")
        if self.health_path != "/health/live" or self.readiness_path != "/health/ready":
            raise ValueError("PILOT_HEALTH_PROBES_REQUIRED")


@dataclass(frozen=True, slots=True)
class OidcRuntimeConfig:
    policy: OidcPolicy
    jwks_uri: str

    def __post_init__(self) -> None:
        parsed = urlsplit(self.jwks_uri)
        loopback = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1", "localhost"}
        issuer = urlsplit(self.policy.issuer)
        if (
            (parsed.scheme != "https" and not (self.policy.allow_insecure_loopback and loopback))
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or (parsed.scheme, parsed.hostname, parsed.port)
            != (issuer.scheme, issuer.hostname, issuer.port)
        ):
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
        if mode is OperatingMode.DEVELOPMENT_PROVIDER_INTEGRATION:
            if any(locations != ("local-development",) for locations in required):
                raise ValueError("DEVELOPMENT_DATA_BOUNDARY_REQUIRED")
            if self.external_processing_locations != ("external-unspecified",):
                raise ValueError("DEVELOPMENT_EXTERNAL_LOCATION_REQUIRED")
            return
        if mode is OperatingMode.LOCAL:
            if any(locations != ("local",) for locations in required):
                raise ValueError("LOCAL_DATA_BOUNDARY_REQUIRED")
            if any(location != "local" for location in self.external_processing_locations):
                raise ValueError("LOCAL_PROVIDER_PROCESSING_REQUIRED")
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
class ProviderAttestation:
    evidence_id: str
    evidence_type: str
    evidence_ref: str
    issuer: str
    issued_at: str
    valid_from: str
    expires_at: str
    verification_status: str
    verified_at: str | None
    verified_by: str | None
    document_hash: str | None


@dataclass(frozen=True, slots=True)
class ProviderEgress:
    provider: str
    service: str
    host: str
    processing_location: str
    confirmed_processing_locations: tuple[str, ...]
    tenant_ids: tuple[str, ...]
    attestation: ProviderAttestation


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
    provider_egress: tuple[ProviderEgress, ...]
    controlled_pilot: ControlledPilotConfig | None
    worker_policy: JobPolicy

    def __post_init__(self) -> None:
        if self.operating_mode is OperatingMode.CONTROLLED_PILOT:
            if self.controlled_pilot is None:
                raise ValueError("CONTROLLED_PILOT_CONFIGURATION_REQUIRED")
        elif self.controlled_pilot is not None:
            raise ValueError("CONTROLLED_PILOT_PROFILE_REQUIRED")
        if self.profile in {EnvironmentProfile.STAGING, EnvironmentProfile.PRODUCTION}:
            if self.operating_mode is None:
                raise ValueError("OPERATING_MODE_REQUIRED")
            if self.data_residency is None:
                raise ValueError("DATA_RESIDENCY_POLICY_REQUIRED")
            if self.operating_mode is OperatingMode.DEVELOPMENT_PROVIDER_INTEGRATION:
                raise ValueError("DEVELOPMENT_PROVIDER_PROFILE_FORBIDDEN")
            self.data_residency.validate_for(self.operating_mode)
            if self.database_backend is not DatabaseBackend.POSTGRESQL:
                raise ValueError("PRODUCTION_REQUIRES_POSTGRESQL")
            if self.authentication_mode is not AuthenticationMode.OIDC or self.oidc is None:
                raise ValueError("PRODUCTION_REQUIRES_OIDC")
            if self.oidc.policy.allow_insecure_loopback:
                raise ValueError("PRODUCTION_OIDC_HTTPS_REQUIRED")
            if not self.oidc.policy.authorized_parties:
                raise ValueError("OIDC_AUTHORIZED_PARTIES_REQUIRED")
            if not self.oidc.policy.required_scopes:
                raise ValueError("OIDC_REQUIRED_SCOPES_REQUIRED")
            if self.secret_provider is not SecretProviderMode.EXTERNAL:
                raise ValueError("EXTERNAL_SECRET_PROVIDER_REQUIRED")
            if not self.egress_allowed_hosts:
                raise ValueError("EGRESS_ALLOWLIST_REQUIRED")
            if not self.provider_egress:
                raise ValueError("PROVIDER_EGRESS_REQUIRED")
            provider_hosts = tuple(item.host for item in self.provider_egress)
            if len(set(provider_hosts)) != len(provider_hosts):
                raise ValueError("DUPLICATE_PROVIDER_EGRESS_HOST")
            if set(provider_hosts) != {
                host.casefold().rstrip(".") for host in self.egress_allowed_hosts
            }:
                raise ValueError("PROVIDER_EGRESS_ALLOWLIST_MISMATCH")
            for provider in self.provider_egress:
                if (
                    self.operating_mode is OperatingMode.LOCAL
                    and provider.processing_location != "local"
                ):
                    raise ValueError("LOCAL_PROVIDER_PROCESSING_REQUIRED")
                if (
                    self.operating_mode is OperatingMode.EU_MANAGED
                    and provider.processing_location not in _EU_COUNTRY_CODES
                ):
                    raise ValueError("EU_PROVIDER_PROCESSING_REQUIRED")
                if (
                    provider.processing_location
                    not in self.data_residency.external_processing_locations
                ):
                    raise ValueError("PROVIDER_PROCESSING_LOCATION_UNDECLARED")
        elif self.operating_mode is not None or self.data_residency is not None:
            if self.operating_mode is not OperatingMode.DEVELOPMENT_PROVIDER_INTEGRATION:
                raise ValueError("DEVELOPMENT_PROVIDER_PROFILE_REQUIRED")
            if self.data_residency is None:
                raise ValueError("DATA_RESIDENCY_POLICY_REQUIRED")
            self.data_residency.validate_for(self.operating_mode)
            if set(item.host for item in self.provider_egress) != {
                host.casefold().rstrip(".") for host in self.egress_allowed_hosts
            }:
                raise ValueError("PROVIDER_EGRESS_ALLOWLIST_MISMATCH")
            if any(
                item.processing_location != "external-unspecified" for item in self.provider_egress
            ):
                raise ValueError("DEVELOPMENT_EXTERNAL_LOCATION_REQUIRED")

    def validate_provider_urls(self, urls: tuple[str, ...]) -> None:
        declared = {item.host for item in self.provider_egress}
        actual: set[str] = set()
        for url in urls:
            try:
                host = (urlsplit(url).hostname or "").casefold().rstrip(".")
            except ValueError:
                raise ValueError("PROVIDER_EGRESS_UNDECLARED") from None
            if not host or host not in declared:
                raise ValueError("PROVIDER_EGRESS_UNDECLARED")
            actual.add(host)
        if actual != declared:
            raise ValueError("PROVIDER_EGRESS_RUNTIME_MISMATCH")

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
                    authorized_parties=_string_tuple(oidc_raw, "authorized_parties"),
                    required_scopes=_string_tuple(oidc_raw, "required_scopes"),
                    allow_insecure_loopback=_boolean(
                        oidc_raw, "allow_insecure_loopback", default=False
                    ),
                ),
                _required(oidc_raw, "jwks_uri"),
            )
        worker = raw.get("worker", {})
        if not isinstance(worker, Mapping):
            raise ValueError("INVALID_WORKER_CONFIGURATION")
        hosts = raw.get("egress_allowed_hosts", [])
        if not isinstance(hosts, list) or any(not isinstance(item, str) for item in hosts):
            raise ValueError("INVALID_EGRESS_ALLOWLIST")
        controlled_pilot_raw = raw.get("controlled_pilot")
        controlled_pilot = (
            _controlled_pilot_config(controlled_pilot_raw)
            if controlled_pilot_raw is not None
            else None
        )
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
            provider_egress=_provider_egress(raw.get("provider_egress", [])),
            controlled_pilot=controlled_pilot,
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


def _required_nonempty(raw: Mapping[str, Any], key: str) -> str:
    value = _required(raw, key).strip()
    if not value:
        raise ValueError(f"INVALID_CONFIG_VALUE:{key}")
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
    development_sentinels = {"local", "local-development", "external-unspecified"}
    return tuple(value if value in development_sentinels else value.upper() for value in values)


def _controlled_pilot_config(raw: object) -> ControlledPilotConfig:
    if not isinstance(raw, Mapping):
        raise ValueError("INVALID_CONTROLLED_PILOT_CONFIGURATION")
    if set(raw).difference(_CONTROLLED_PILOT_FIELDS):
        raise ValueError("UNKNOWN_CONTROLLED_PILOT_FIELD")
    audit_persistence = raw.get("audit_persistence")
    if not isinstance(audit_persistence, bool):
        raise ValueError("PILOT_AUDIT_PERSISTENCE_REQUIRED")
    return ControlledPilotConfig(
        public_base_url=_required_nonempty(raw, "public_base_url"),
        oidc_redirect_uri=_required_nonempty(raw, "oidc_redirect_uri"),
        post_logout_redirect_uri=_required_nonempty(raw, "post_logout_redirect_uri"),
        allowed_hosts=_string_tuple(raw, "allowed_hosts"),
        trusted_proxy_cidrs=_string_tuple(raw, "trusted_proxy_cidrs"),
        audit_persistence=audit_persistence,
        backup_configuration_ref=_required_nonempty(raw, "backup_configuration_ref"),
        lifecycle_pseudonymization_secret=_pilot_secret_reference(
            raw, "lifecycle_pseudonymization_secret"
        ),
        session_pepper_secret=_pilot_secret_reference(raw, "session_pepper_secret"),
        session_envelope_key_secret=_pilot_secret_reference(raw, "session_envelope_key_secret"),
        export_signing=SigningSettings.from_mapping(_required_mapping(raw, "export_signing")),
        retention_days=int(raw.get("retention_days", 0)),
        pilot_tenant=_required(raw, "pilot_tenant"),
        health_path=_required(raw, "health_path"),
        readiness_path=_required(raw, "readiness_path"),
    )


def _pilot_secret_reference(raw: Mapping[str, Any], key: str) -> SecretReference:
    value = _required_nonempty(raw, key)
    if value.casefold() in {"example", "default", "placeholder", "changeme"}:
        raise ValueError("PILOT_SECRET_REFERENCE_REQUIRED")
    try:
        return SecretReference(value)
    except ValueError:
        raise ValueError("PILOT_SECRET_REFERENCE_REQUIRED") from None


def _required_mapping(raw: Mapping[str, Any], key: str) -> Mapping[str, object]:
    value = raw.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"INVALID_CONFIG_VALUE:{key}")
    return value


def _string_tuple(raw: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"INVALID_CONFIG_VALUE:{key}")
    normalized = tuple(item.strip() for item in value)
    if any(not item for item in normalized) or len(set(normalized)) != len(normalized):
        raise ValueError(f"INVALID_CONFIG_VALUE:{key}")
    return normalized


def _provider_egress(raw: object) -> tuple[ProviderEgress, ...]:
    if not isinstance(raw, list):
        raise ValueError("INVALID_PROVIDER_EGRESS")
    providers: list[ProviderEgress] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("INVALID_PROVIDER_EGRESS")
        if set(item).difference(_PROVIDER_EGRESS_FIELDS):
            raise ValueError("UNKNOWN_PROVIDER_EGRESS_FIELD")
        attestation_raw = item.get("attestation")
        if not isinstance(attestation_raw, Mapping):
            raise ValueError("PROVIDER_ATTESTATION_REQUIRED")
        if set(attestation_raw).difference(_ATTESTATION_FIELDS):
            raise ValueError("UNKNOWN_PROVIDER_ATTESTATION_FIELD")
        host = _required_nonempty(item, "host").casefold().rstrip(".")
        location = _required_nonempty(item, "processing_location")
        confirmed_locations = _locations(item, "confirmed_processing_locations")
        provider = _required_nonempty(item, "provider")
        service = _required_nonempty(item, "service")
        tenant_ids = _string_tuple(item, "tenant_ids")
        if not tenant_ids:
            raise ValueError("PROVIDER_TENANT_SCOPE_REQUIRED")
        evidence_type = _required_nonempty(attestation_raw, "evidence_type")
        if evidence_type not in _EVIDENCE_TYPES:
            raise ValueError("INVALID_PROVIDER_EVIDENCE_TYPE")
        verification_status = _required_nonempty(attestation_raw, "verification_status")
        if verification_status not in _VERIFICATION_STATUSES:
            raise ValueError("INVALID_PROVIDER_VERIFICATION_STATUS")
        evidence_ref = _required_nonempty(attestation_raw, "evidence_ref")
        issuer = _required_nonempty(attestation_raw, "issuer")
        issued_at = _required_nonempty(attestation_raw, "issued_at")
        valid_from = _required_nonempty(attestation_raw, "valid_from")
        expires_at = _required_nonempty(attestation_raw, "expires_at")
        evidence_id = _required_nonempty(attestation_raw, "evidence_id")
        providers.append(
            ProviderEgress(
                provider=provider,
                service=service,
                host=host,
                processing_location=(
                    location if location in {"local", "external-unspecified"} else location.upper()
                ),
                confirmed_processing_locations=confirmed_locations,
                tenant_ids=tenant_ids,
                attestation=ProviderAttestation(
                    evidence_id=evidence_id,
                    evidence_type=evidence_type,
                    evidence_ref=evidence_ref,
                    issuer=issuer,
                    issued_at=issued_at,
                    valid_from=valid_from,
                    expires_at=expires_at,
                    verification_status=verification_status,
                    verified_at=_optional_string(attestation_raw, "verified_at"),
                    verified_by=_optional_string(attestation_raw, "verified_by"),
                    document_hash=_optional_string(attestation_raw, "document_hash"),
                ),
            )
        )
    return tuple(providers)


def _optional_string(raw: Mapping[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"INVALID_CONFIG_VALUE:{key}")
    return value.strip()


def _boolean(raw: Mapping[str, Any], key: str, *, default: bool) -> bool:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"INVALID_CONFIG_VALUE:{key}")
    return value


def _reject_literal_secrets(raw: Mapping[str, Any]) -> None:
    forbidden = {"password", "api_key", "token", "secret_value", "database_dsn"}
    for key, value in raw.items():
        if key.casefold() in forbidden:
            raise ValueError("LITERAL_SECRET_FORBIDDEN")
        if isinstance(value, Mapping):
            _reject_literal_secrets(value)
