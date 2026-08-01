from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_SHA = re.compile(r"^[0-9a-f]{40,64}$")


class EnvironmentProfile(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class OperatingMode(str, Enum):
    DEVELOPMENT_PROVIDER_INTEGRATION = "development-provider-integration"
    LOCAL = "local"
    EU_MANAGED = "eu-managed"
    CONTROLLED_PILOT = "controlled-pilot"


class DatabaseBackend(str, Enum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


class AuthenticationMode(str, Enum):
    STATIC = "static"
    OIDC = "oidc"


class SecretProviderMode(str, Enum):
    ENVIRONMENT = "environment"
    EXTERNAL = "external"


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DEAD_LETTER = "DEAD_LETTER"


class ReleaseStatus(str, Enum):
    PASS = "PASS"  # noqa: S105 - release state, not a credential
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class SecretReference:
    name: str
    required: bool = True

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.name):
            raise ValueError("INVALID_SECRET_REFERENCE")


@dataclass(frozen=True, slots=True, repr=False)
class SecretValue:
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("EMPTY_SECRET")

    def __repr__(self) -> str:
        return "SecretValue(**redacted**)"


@dataclass(frozen=True, slots=True)
class OidcPolicy:
    issuer: str
    audience: str
    algorithms: tuple[str, ...]
    tenant_claim: str = "tenant_id"
    actor_id_claim: str = "sub"
    role_claim: str = "role"
    actor_kind_claim: str = "actor_kind"
    organization_claim: str | None = None
    groups_claim: str | None = None
    clock_skew_seconds: int = 30
    authorized_parties: tuple[str, ...] = ()
    required_scopes: tuple[str, ...] = ()
    allow_insecure_loopback: bool = False

    def __post_init__(self) -> None:
        issuer = urlsplit(self.issuer)
        loopback = issuer.scheme == "http" and issuer.hostname in {"127.0.0.1", "::1", "localhost"}
        if (
            (issuer.scheme != "https" and not (self.allow_insecure_loopback and loopback))
            or not issuer.hostname
            or issuer.username is not None
            or issuer.password is not None
            or bool(issuer.query)
            or bool(issuer.fragment)
            or not self.audience.strip()
        ):
            raise ValueError("INVALID_OIDC_TRUST_CONFIGURATION")
        if not self.algorithms or any(item not in {"RS256", "ES256"} for item in self.algorithms):
            raise ValueError("INVALID_OIDC_ALGORITHM_ALLOWLIST")
        claims = (
            self.tenant_claim,
            self.actor_id_claim,
            self.role_claim,
            self.actor_kind_claim,
        )
        if any(not item.strip() for item in claims):
            raise ValueError("INVALID_OIDC_CLAIM_MAPPING")
        if not 0 <= self.clock_skew_seconds <= 120:
            raise ValueError("INVALID_OIDC_CLOCK_SKEW")
        if any(not item.strip() or len(item) > 256 for item in self.authorized_parties):
            raise ValueError("INVALID_OIDC_AUTHORIZED_PARTY")
        if any(not item.strip() or len(item) > 128 for item in self.required_scopes):
            raise ValueError("INVALID_OIDC_REQUIRED_SCOPE")


@dataclass(frozen=True, slots=True)
class JobPolicy:
    max_attempts: int = 5
    lease_seconds: int = 60
    base_backoff_seconds: int = 5
    maximum_backoff_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 20:
            raise ValueError("INVALID_JOB_ATTEMPT_LIMIT")
        if not 5 <= self.lease_seconds <= 3600:
            raise ValueError("INVALID_JOB_LEASE")
        if not 1 <= self.base_backoff_seconds <= self.maximum_backoff_seconds <= 86_400:
            raise ValueError("INVALID_JOB_BACKOFF")


@dataclass(frozen=True, slots=True)
class ResearchJob:
    job_id: str
    tenant_id: str
    research_run_id: str
    correlation_id: str
    payload_hash: str
    status: JobStatus
    attempt_count: int
    available_at: str
    created_at: str
    updated_at: str
    lease_token_hash: str | None = None
    lease_expires_at: str | None = None

    def __post_init__(self) -> None:
        identifiers = (self.job_id, self.tenant_id, self.research_run_id, self.correlation_id)
        if any(not _ID.fullmatch(item) for item in identifiers):
            raise ValueError("INVALID_JOB_IDENTITY")
        if not self.payload_hash.startswith("sha256:") or len(self.payload_hash) != 71:
            raise ValueError("INVALID_JOB_PAYLOAD_HASH")
        if self.attempt_count < 0:
            raise ValueError("INVALID_JOB_ATTEMPT_COUNT")
        if (self.lease_token_hash is None) != (self.lease_expires_at is None):
            raise ValueError("INCOMPLETE_JOB_LEASE")


@dataclass(frozen=True, slots=True)
class GateResult:
    gate_id: str
    status: ReleaseStatus
    reason_codes: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.gate_id):
            raise ValueError("INVALID_RELEASE_GATE_ID")
        if self.status is not ReleaseStatus.PASS and not self.reason_codes:
            raise ValueError("RELEASE_GATE_REASON_REQUIRED")
        if not self.evidence_refs:
            raise ValueError("RELEASE_GATE_EVIDENCE_REQUIRED")


@dataclass(frozen=True, slots=True)
class ReleaseVerificationReport:
    version: str
    commit_sha: str
    generated_at: str
    gates: tuple[GateResult, ...]
    schema_version: str = "0.5.0"

    def __post_init__(self) -> None:
        if self.schema_version != "0.5.0" or self.version != "0.5.0":
            raise ValueError("INVALID_RELEASE_REPORT_VERSION")
        if not _SHA.fullmatch(self.commit_sha):
            raise ValueError("INVALID_BUILD_COMMIT")
        if not self.gates or len({item.gate_id for item in self.gates}) != len(self.gates):
            raise ValueError("INVALID_RELEASE_GATES")

    @property
    def status(self) -> ReleaseStatus:
        values = {item.status for item in self.gates}
        if ReleaseStatus.BLOCK in values:
            return ReleaseStatus.BLOCK
        if ReleaseStatus.REVIEW in values:
            return ReleaseStatus.REVIEW
        return ReleaseStatus.PASS


@dataclass(frozen=True, slots=True)
class HealthComponent:
    component: str
    status: HealthStatus
    reason_code: str | None = None
    critical: bool = True

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.component):
            raise ValueError("INVALID_HEALTH_COMPONENT")
        if self.status is not HealthStatus.HEALTHY and not self.reason_code:
            raise ValueError("HEALTH_REASON_REQUIRED")


@dataclass(frozen=True, slots=True)
class HealthReport:
    components: tuple[HealthComponent, ...]
    checked_at: str
    schema_version: str = "0.5.0"

    @property
    def ready(self) -> bool:
        return all(
            item.status is not HealthStatus.UNAVAILABLE or not item.critical
            for item in self.components
        )


@dataclass(frozen=True, slots=True)
class BuildMetadata:
    version: str
    commit_sha: str
    build_timestamp: str
    database_schema_version: str

    def __post_init__(self) -> None:
        if self.version != "0.5.0" or not _SHA.fullmatch(self.commit_sha):
            raise ValueError("INVALID_BUILD_METADATA")


@dataclass(frozen=True, slots=True)
class PilotProfile:
    profile_id: str
    use_case: str
    maximum_users: int
    maximum_tenants: int
    maximum_research_budget: int
    maximum_research_concurrency: int
    supported_locales: tuple[str, ...]
    supported_providers: tuple[str, ...]
    allowed_data_classes: tuple[str, ...]
    retention_days: int
    feature_flags: tuple[str, ...]
    escalation_process: str
    stop_criteria: tuple[str, ...]
    human_approval_required: bool = True
    schema_version: str = "0.5.0"

    def __post_init__(self) -> None:
        if self.schema_version != "0.5.0" or not _ID.fullmatch(self.profile_id):
            raise ValueError("INVALID_PILOT_PROFILE")
        limits = (
            self.maximum_users,
            self.maximum_tenants,
            self.maximum_research_budget,
            self.maximum_research_concurrency,
            self.retention_days,
        )
        if any(item < 1 for item in limits):
            raise ValueError("INVALID_PILOT_LIMIT")
        if not self.human_approval_required:
            raise ValueError("HUMAN_APPROVAL_REQUIRED")
        if not {"de", "en"}.issubset(self.supported_locales):
            raise ValueError("PILOT_LOCALES_REQUIRED")
        if (
            not self.allowed_data_classes
            or not self.escalation_process.strip()
            or not self.stop_criteria
        ):
            raise ValueError("INCOMPLETE_PILOT_GOVERNANCE")
