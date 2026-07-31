from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast
from urllib.parse import urlsplit, urlunsplit

from ..tenancy import TenantContext
from .config import RuntimeConfig
from .contracts import EnvironmentProfile, OperatingMode

_HOST = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


class EgressRejected(PermissionError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class EgressDecision:
    decision: str
    occurred_at: str
    tenant_id: str
    actor_id: str
    correlation_id: str
    operating_profile: str
    policy_version: str
    provider: str
    connector: str
    target_host: str
    requested_processing_location: str | None
    evidence_id: str | None
    evidence_status: str | None
    reason_code: str


@dataclass(frozen=True, slots=True)
class EgressRequestContext:
    tenant_id: str
    actor_id: str
    correlation_id: str
    record_decision: Callable[[EgressDecision], None]


_CURRENT_CONTEXT: ContextVar[EgressRequestContext | None] = ContextVar(
    "decision_assurance_egress_context", default=None
)


@contextmanager
def bind_egress_context(context: EgressRequestContext) -> Iterator[None]:
    token = _CURRENT_CONTEXT.set(context)
    try:
        yield
    finally:
        _CURRENT_CONTEXT.reset(token)


def current_egress_context() -> EgressRequestContext | None:
    return _CURRENT_CONTEXT.get()


class HttpsEgressAllowlist:
    def __init__(self, hosts: tuple[str, ...]):
        normalized = tuple(sorted({item.casefold().rstrip(".") for item in hosts}))
        if not normalized or any(not _valid_public_hostname(item) for item in normalized):
            raise ValueError("INVALID_EGRESS_ALLOWLIST")
        self._hosts = frozenset(normalized)

    def validate(self, tenant: TenantContext, url: str) -> str:
        del tenant
        try:
            parsed = urlsplit(url)
            host = (parsed.hostname or "").casefold().rstrip(".")
            port = parsed.port
        except ValueError:
            raise EgressRejected("EGRESS_REJECTED") from None
        if (
            parsed.scheme != "https"
            or not host
            or host not in self._hosts
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
            or not _valid_public_hostname(host)
        ):
            raise EgressRejected("EGRESS_REJECTED")
        return urlunsplit(("https", parsed.netloc.casefold(), parsed.path or "/", parsed.query, ""))


class ResidencyEgressGuard:
    """Fail-closed request-time residency, attestation and tenant guard."""

    policy_version = "residency-policy-v1"

    def __init__(
        self,
        config_supplier: Callable[[], RuntimeConfig | None],
        *,
        clock: Callable[[], datetime] | None = None,
        expected_profile: EnvironmentProfile | None = None,
    ) -> None:
        self._config_supplier = config_supplier
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._expected_profile = expected_profile

    def authorize_current(self, *, provider: str, connector: str, url: str) -> str:
        context = current_egress_context()
        if context is None:
            raise EgressRejected("EGRESS_CONTEXT_REQUIRED")
        return self.authorize(context, provider=provider, connector=connector, url=url)

    def authorize(
        self,
        context: EgressRequestContext,
        *,
        provider: str,
        connector: str,
        url: str,
    ) -> str:
        now = self._clock().astimezone(timezone.utc)
        parsed_host = self._host(url)
        try:
            config = self._config_supplier()
        except Exception:
            config = None
        profile = getattr(getattr(config, "profile", None), "value", "unknown")
        location: str | None = None
        evidence_id: str | None = None
        evidence_status: str | None = None

        def decide(decision: str, reason_code: str, *, allowed_url: str | None = None) -> str:
            decision_event = EgressDecision(
                decision=decision,
                occurred_at=now.isoformat(),
                tenant_id=context.tenant_id,
                actor_id=context.actor_id,
                correlation_id=context.correlation_id,
                operating_profile=profile,
                policy_version=self.policy_version,
                provider=provider,
                connector=connector,
                target_host=parsed_host,
                requested_processing_location=location,
                evidence_id=evidence_id,
                evidence_status=evidence_status,
                reason_code=reason_code,
            )
            try:
                context.record_decision(decision_event)
            except Exception as error:
                raise EgressRejected("EGRESS_AUDIT_FAILED") from error
            if decision != "ALLOWED":
                raise EgressRejected(reason_code)
            return cast(str, allowed_url)

        if config is None:
            return decide("BLOCKED", "EGRESS_CONFIGURATION_CHANGED")
        if self._expected_profile is not None and config.profile is not self._expected_profile:
            return decide("BLOCKED", "EGRESS_CONFIGURATION_CHANGED")
        mode = getattr(config, "operating_mode", None)
        residency = getattr(config, "data_residency", None)
        if mode is None or residency is None:
            return decide("BLOCKED", "EGRESS_RESIDENCY_POLICY_MISSING")
        try:
            residency.validate_for(mode)
        except (AttributeError, ValueError):
            return decide("BLOCKED", "EGRESS_CONFIGURATION_CHANGED")
        try:
            normalized_url = HttpsEgressAllowlist(config.egress_allowed_hosts).validate(
                TenantContext(context.tenant_id), url
            )
        except (ValueError, EgressRejected):
            return decide("BLOCKED", "EGRESS_HOST_MISMATCH")
        egress = next(
            (
                item
                for item in config.provider_egress
                if item.host == parsed_host and item.provider == provider
            ),
            None,
        )
        if egress is None:
            return decide("BLOCKED", "EGRESS_HOST_MISMATCH")
        if egress.service != connector:
            return decide("BLOCKED", "EGRESS_HOST_MISMATCH")
        location = egress.processing_location
        attestation = egress.attestation
        evidence_id = attestation.evidence_id
        evidence_status = attestation.verification_status
        if "*" not in egress.tenant_ids and context.tenant_id not in egress.tenant_ids:
            return decide("BLOCKED", "EGRESS_TENANT_MISMATCH")
        if location not in residency.external_processing_locations:
            return decide("BLOCKED", "EGRESS_LOCATION_NOT_ALLOWED")
        is_development = (
            config.profile is EnvironmentProfile.DEVELOPMENT
            and mode is OperatingMode.DEVELOPMENT_PROVIDER_INTEGRATION
        )
        if is_development:
            if (
                location != "external-unspecified"
                or attestation.evidence_type != "OPERATOR_SELF_DECLARATION"
                or attestation.verification_status != "UNVERIFIED"
            ):
                return decide("BLOCKED", "EGRESS_CONFIGURATION_CHANGED")
            return decide("ALLOWED", "EGRESS_ALLOWED_DEVELOPMENT", allowed_url=normalized_url)
        if attestation.evidence_type == "OPERATOR_SELF_DECLARATION":
            return decide("BLOCKED", "EGRESS_EVIDENCE_UNVERIFIED")
        if attestation.verification_status != "VERIFIED":
            reason = (
                "EGRESS_EVIDENCE_EXPIRED"
                if attestation.verification_status == "EXPIRED"
                else "EGRESS_EVIDENCE_UNVERIFIED"
            )
            return decide("BLOCKED", reason)
        if not attestation.verified_at or not attestation.verified_by:
            return decide("BLOCKED", "EGRESS_EVIDENCE_UNVERIFIED")
        try:
            issued_at = _parse_time(attestation.issued_at)
            valid_from = _parse_time(attestation.valid_from)
            expires_at = _parse_time(attestation.expires_at)
            verified_at = _parse_time(attestation.verified_at)
        except ValueError:
            return decide("BLOCKED", "EGRESS_EVIDENCE_UNVERIFIED")
        if expires_at <= now:
            return decide("BLOCKED", "EGRESS_EVIDENCE_EXPIRED")
        if issued_at > now or valid_from > now or verified_at > now or valid_from >= expires_at:
            return decide("BLOCKED", "EGRESS_EVIDENCE_UNVERIFIED")
        if attestation.evidence_type not in {
            "DPA",
            "SIGNED_PROVIDER_ATTESTATION",
            "TECHNICAL_PROVIDER_CONFIGURATION",
        }:
            return decide("BLOCKED", "EGRESS_EVIDENCE_UNVERIFIED")
        confirmed_locations = getattr(egress, "confirmed_processing_locations", ())
        if not confirmed_locations:
            return decide("BLOCKED", "EGRESS_EVIDENCE_MISSING")
        if location not in confirmed_locations:
            return decide("BLOCKED", "EGRESS_LOCATION_NOT_ALLOWED")
        if not attestation.evidence_ref.startswith("https://") or not attestation.issuer:
            return decide("BLOCKED", "EGRESS_EVIDENCE_UNVERIFIED")
        return decide("ALLOWED", "EGRESS_ALLOWED", allowed_url=normalized_url)

    @staticmethod
    def _host(url: str) -> str:
        try:
            return (urlsplit(url).hostname or "").casefold().rstrip(".")
        except ValueError:
            return ""


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return parsed.astimezone(timezone.utc)


def _valid_public_hostname(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        return bool(_HOST.fullmatch(host)) and host != "localhost" and not host.endswith(".local")
