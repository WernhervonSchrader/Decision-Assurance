from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


class MfaRequired(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MfaEvidence:
    acr: str
    amr: tuple[str, ...]
    authenticated_at: datetime
    policy_version: str


@dataclass(frozen=True, slots=True)
class MfaPolicy:
    version: str
    required_roles: frozenset[str]
    allowed_acr: frozenset[str]
    allowed_methods: frozenset[str]
    max_auth_age: timedelta

    def require(
        self,
        roles: frozenset[str],
        evidence: MfaEvidence | None,
        *,
        now: datetime,
    ) -> None:
        if not roles.intersection(self.required_roles):
            return
        instant = now.astimezone(timezone.utc)
        if (
            evidence is None
            or evidence.acr not in self.allowed_acr
            or not set(evidence.amr).intersection(self.allowed_methods)
            or evidence.policy_version != self.version
            or evidence.authenticated_at.tzinfo is None
            or instant - evidence.authenticated_at.astimezone(timezone.utc) > self.max_auth_age
            or evidence.authenticated_at.astimezone(timezone.utc) > instant
        ):
            raise MfaRequired("MFA_REQUIRED")


def evidence_from_validated_claims(
    claims: Mapping[str, object], *, policy_version: str
) -> MfaEvidence | None:
    acr = claims.get("acr")
    amr = claims.get("amr")
    auth_time = claims.get("auth_time")
    if not isinstance(acr, str) or not isinstance(amr, list) or not isinstance(auth_time, int):
        return None
    if any(not isinstance(value, str) or not value for value in amr):
        return None
    return MfaEvidence(
        acr=acr,
        amr=tuple(amr),
        authenticated_at=datetime.fromtimestamp(auth_time, tz=timezone.utc),
        policy_version=policy_version,
    )
