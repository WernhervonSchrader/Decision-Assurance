from __future__ import annotations

import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from importlib.resources import files
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

from ..identity import ActorKind, Identity, Role

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40,64}$")
REQUIRED_EVIDENCE = frozenset(
    {
        "TLS_CERTIFICATE_EVIDENCE",
        "PUBLIC_HOST_EVIDENCE",
        "EDGE_CONFIGURATION_EVIDENCE",
        "OIDC_REDIRECT_EVIDENCE",
        "MFA_POLICY_EVIDENCE",
        "DATABASE_MIGRATION_EVIDENCE",
        "RECOVERY_EVIDENCE",
        "MONITORING_EVIDENCE",
        "ALERT_TEST_EVIDENCE",
        "MULTI_INSTANCE_EVIDENCE",
        "SIGNED_EXPORT_EVIDENCE",
        "RETENTION_LEGAL_HOLD_EVIDENCE",
        "INDEPENDENT_REVIEW_EVIDENCE",
    }
)


class EvidenceStatus(str, Enum):
    INCOMPLETE = "INCOMPLETE"
    TECHNICALLY_VERIFIED = "TECHNICALLY_VERIFIED"
    PILOT_REVIEW_REQUIRED = "PILOT_REVIEW_REQUIRED"
    PILOT_ACCEPTED = "PILOT_ACCEPTED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    kind: str
    verified: bool
    observed_at: datetime
    digest: str
    source: str
    deployment_id: str
    tenant_id: str
    commit_sha: str

    def __post_init__(self) -> None:
        if self.kind not in REQUIRED_EVIDENCE or not _DIGEST.fullmatch(self.digest):
            raise ValueError("INVALID_EVIDENCE_DIGEST")
        if self.source not in {"MEASURED", "REPOSITORY", "SELF_DECLARED"}:
            raise ValueError("INVALID_EVIDENCE_SOURCE")
        if self.observed_at.tzinfo is None:
            raise ValueError("INVALID_EVIDENCE_TIME")
        if not self.deployment_id or not self.tenant_id or not _COMMIT.fullmatch(self.commit_sha):
            raise ValueError("UNBOUND_DEPLOYMENT_EVIDENCE")

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "verified": self.verified,
            "observed_at": self.observed_at.isoformat().replace("+00:00", "Z"),
            "digest": self.digest,
            "source": self.source,
            "deployment_id": self.deployment_id,
            "tenant_id": self.tenant_id,
            "commit_sha": self.commit_sha,
        }


@dataclass(frozen=True, slots=True)
class DeploymentBundle:
    schema_version: str
    deployment_id: str
    tenant_id: str
    profile: str
    commit_sha: str
    image_digests: Mapping[str, str]
    sbom_checksums: Mapping[str, str]
    config_checksums: Mapping[str, str]
    evidence: tuple[EvidenceItem, ...]
    provider_residency_status: str
    open_risks: tuple[str, ...]
    creator: str
    created_at: datetime

    def __post_init__(self) -> None:
        if (
            self.schema_version != "1.0.0"
            or not self.deployment_id
            or not self.tenant_id
            or self.profile != "controlled-pilot"
            or not _COMMIT.fullmatch(self.commit_sha)
            or not self.creator
            or self.created_at.tzinfo is None
        ):
            raise ValueError("INVALID_DEPLOYMENT_BUNDLE")
        for values in (self.image_digests, self.sbom_checksums, self.config_checksums):
            if not values or any(not _DIGEST.fullmatch(value) for value in values.values()):
                raise ValueError("INVALID_DEPLOYMENT_DIGEST")
        if len({item.kind for item in self.evidence}) != len(self.evidence):
            raise ValueError("DUPLICATE_DEPLOYMENT_EVIDENCE")
        if self.provider_residency_status not in {"VERIFIED", "ACCESS_BLOCKED"}:
            raise ValueError("INVALID_PROVIDER_RESIDENCY_STATUS")
        if not self.open_risks or any(not risk.strip() for risk in self.open_risks):
            raise ValueError("UNDOCUMENTED_DEPLOYMENT_RISK")

    def with_evidence(self, evidence: tuple[EvidenceItem, ...]) -> DeploymentBundle:
        return replace(self, evidence=evidence)

    def with_created_at(self, created_at: datetime) -> DeploymentBundle:
        return replace(self, created_at=created_at)

    def as_dict(self, status: EvidenceStatus = EvidenceStatus.INCOMPLETE) -> dict[str, object]:
        if status is EvidenceStatus.PILOT_ACCEPTED:
            raise ValueError("ACCEPTANCE_RECORD_REQUIRED")
        return {
            "schema_version": self.schema_version,
            "deployment_id": self.deployment_id,
            "tenant_id": self.tenant_id,
            "profile": self.profile,
            "commit_sha": self.commit_sha,
            "image_digests": dict(self.image_digests),
            "sbom_checksums": dict(self.sbom_checksums),
            "config_checksums": dict(self.config_checksums),
            "evidence": [item.as_dict() for item in self.evidence],
            "provider_residency_status": self.provider_residency_status,
            "open_risks": list(self.open_risks),
            "creator": self.creator,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "status": status.value,
        }


@dataclass(frozen=True, slots=True)
class GateResult:
    status: EvidenceStatus
    reasons: tuple[str, ...]


class PilotAcceptanceGate:
    def __init__(self, *, max_age: timedelta):
        self._max_age = max_age

    def evaluate(self, bundle: DeploymentBundle, *, now: datetime) -> GateResult:
        reasons: list[str] = []
        by_kind = {item.kind: item for item in bundle.evidence}
        missing = sorted(REQUIRED_EVIDENCE - set(by_kind))
        if missing:
            reasons.append("MISSING_EVIDENCE:" + ",".join(missing))
        if any(not item.verified for item in by_kind.values()):
            reasons.append("UNVERIFIED_EVIDENCE")
        if any(item.source == "SELF_DECLARED" for item in by_kind.values()):
            reasons.append("SELF_DECLARED_EVIDENCE")
        if any(
            item.deployment_id != bundle.deployment_id
            or item.tenant_id != bundle.tenant_id
            or item.commit_sha != bundle.commit_sha
            for item in by_kind.values()
        ):
            reasons.append("EVIDENCE_BINDING_MISMATCH")
        instant = now.astimezone(timezone.utc)
        if any(
            instant - item.observed_at.astimezone(timezone.utc) > self._max_age
            for item in by_kind.values()
        ):
            reasons.append("STALE_REQUIRED_EVIDENCE")
        if any(item.observed_at.astimezone(timezone.utc) > instant for item in by_kind.values()):
            reasons.append("FUTURE_REQUIRED_EVIDENCE")
        if instant - bundle.created_at.astimezone(timezone.utc) > self._max_age:
            reasons.append("STALE_DEPLOYMENT_EVIDENCE")
        if bundle.created_at.astimezone(timezone.utc) > instant:
            reasons.append("FUTURE_DEPLOYMENT_EVIDENCE")
        status = EvidenceStatus.PILOT_REVIEW_REQUIRED if not reasons else EvidenceStatus.BLOCKED
        return GateResult(status, tuple(reasons))


@dataclass(frozen=True, slots=True)
class AcceptanceRecord:
    status: EvidenceStatus
    deployment_id: str
    creator: str
    reviewer: str


class PilotAcceptanceTransition:
    def accept(
        self,
        bundle: DeploymentBundle,
        technical_result: GateResult,
        *,
        reviewer: Identity,
    ) -> AcceptanceRecord:
        if technical_result.status is not EvidenceStatus.PILOT_REVIEW_REQUIRED:
            raise ValueError("TECHNICAL_EVIDENCE_GATE_REQUIRED")
        if reviewer.kind is not ActorKind.HUMAN or Role.REVIEWER not in reviewer.roles:
            raise ValueError("PILOT_REVIEWER_REQUIRED")
        if reviewer.tenant.tenant_id != bundle.tenant_id:
            raise ValueError("ACCEPTANCE_TENANT_MISMATCH")
        if hmac.compare_digest(bundle.creator, reviewer.actor_id):
            raise ValueError("ACCEPTANCE_ACTOR_INDEPENDENCE_REQUIRED")
        return AcceptanceRecord(
            EvidenceStatus.PILOT_ACCEPTED,
            bundle.deployment_id,
            bundle.creator,
            reviewer.actor_id,
        )


@dataclass(frozen=True, slots=True)
class TlsEvidence:
    host: str
    certificate_hosts: tuple[str, ...]
    not_before: datetime
    not_after: datetime
    chain_verified: bool
    minimum_tls: str
    source: str

    def verify(self, expected_host: str, now: datetime) -> None:
        host = expected_host.casefold().rstrip(".")
        names = tuple(value.casefold().rstrip(".") for value in self.certificate_hosts)
        if not hmac.compare_digest(self.host.casefold().rstrip("."), host):
            raise ValueError("TLS_HOST_MISMATCH")
        if not any(_certificate_name_matches(host, name) for name in names):
            raise ValueError("TLS_CERTIFICATE_HOST_MISMATCH")
        instant = now.astimezone(timezone.utc)
        if (
            self.not_before.tzinfo is None
            or self.not_after.tzinfo is None
            or not (self.not_before <= instant <= self.not_after)
        ):
            raise ValueError("TLS_CERTIFICATE_EXPIRED")
        if not self.chain_verified:
            raise ValueError("TLS_CHAIN_UNVERIFIED")
        if self.minimum_tls not in {"1.2", "1.3"} or self.source != "MEASURED":
            raise ValueError("TLS_EVIDENCE_UNVERIFIED")


def load_deployment_bundle(content: bytes) -> DeploymentBundle:
    if not content or len(content) > 2_000_000:
        raise ValueError("DEPLOYMENT_BUNDLE_SIZE_REJECTED")
    try:
        raw = cast(dict[str, Any], json.loads(content))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("INVALID_DEPLOYMENT_BUNDLE") from None
    schema = json.loads(
        files("decision_assurance.schemas")
        .joinpath("production/deployment-evidence.schema.json")
        .read_text(encoding="utf-8")
    )
    if list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(raw)):
        raise ValueError("INVALID_DEPLOYMENT_BUNDLE")
    if _contains_sensitive_key(raw):
        raise ValueError("SENSITIVE_DEPLOYMENT_EVIDENCE")
    items = tuple(
        EvidenceItem(
            str(item["kind"]),
            bool(item["verified"]),
            _parse_time(item["observed_at"]),
            str(item["digest"]),
            str(item["source"]),
            str(item["deployment_id"]),
            str(item["tenant_id"]),
            str(item["commit_sha"]),
        )
        for item in raw["evidence"]
    )
    return DeploymentBundle(
        str(raw["schema_version"]),
        str(raw["deployment_id"]),
        str(raw["tenant_id"]),
        str(raw["profile"]),
        str(raw["commit_sha"]),
        dict(raw["image_digests"]),
        dict(raw["sbom_checksums"]),
        dict(raw["config_checksums"]),
        items,
        str(raw["provider_residency_status"]),
        tuple(raw["open_risks"]),
        str(raw["creator"]),
        _parse_time(raw["created_at"]),
    )


def _parse_time(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("INVALID_EVIDENCE_TIME") from None
    if parsed.tzinfo is None:
        raise ValueError("INVALID_EVIDENCE_TIME")
    return parsed


def _contains_sensitive_key(value: object) -> bool:
    forbidden = {"password", "token", "private_key", "secret", "api_key", "authorization"}
    if isinstance(value, dict):
        return any(
            str(key).casefold() in forbidden or _contains_sensitive_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def _certificate_name_matches(host: str, certificate_name: str) -> bool:
    if "*" not in certificate_name:
        return hmac.compare_digest(host, certificate_name)
    if not certificate_name.startswith("*.") or certificate_name.count("*") != 1:
        return False
    suffix = certificate_name[2:]
    label, separator, remainder = host.partition(".")
    return bool(label and separator) and hmac.compare_digest(remainder, suffix)
