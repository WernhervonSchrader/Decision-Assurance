"""Server-owned verification authority; submitted evidence never supplies this port.

A matching digest is an integrity binding, not source authentication. Only a trusted,
independent verifier may provision records. The in-memory adapter is for development;
production write authorization, persistence and revocation require separate review.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from ..audit import payload_hash


def evidence_binding(data: Mapping[str, Any], evidence: Mapping[str, Any]) -> str:
    """Bind source metadata AND the claims/policy for which it was verified."""
    return payload_hash(
        {
            "purpose": "decision-assurance.source-verification.v1",
            "decision_id": data["decision_id"],
            "claim": data.get("claim", ""),
            "claims": data.get("claims", []),
            "policy_version": data.get("policy_version", "unspecified"),
            "policies": data.get("policies", []),
            "evidence": dict(evidence),
        }
    )


@dataclass(frozen=True, slots=True)
class EvidenceVerification:
    verification_id: str
    tenant_id: str
    decision_id: str
    evidence_id: str
    generator_id: str
    validator_id: str
    binding_hash: str
    verified_at: datetime
    valid_until: datetime
    revoked: bool = False

    def matches(
        self,
        *,
        tenant_id: str,
        generator_id: str,
        decision_id: str,
        evidence_id: str,
        binding_hash: str,
        now: datetime,
    ) -> bool:
        return (
            bool(self.verification_id and self.validator_id and self.generator_id)
            and self.validator_id != generator_id
            and self.tenant_id == tenant_id
            and self.generator_id == generator_id
            and self.decision_id == decision_id
            and self.evidence_id == evidence_id
            and self.binding_hash == binding_hash
            and not self.revoked
            and all(t.utcoffset() is not None for t in (self.verified_at, self.valid_until, now))
            and self.verified_at <= now < self.valid_until
        )


class EvidenceRegistry(Protocol):
    """Read-only trusted port. Never construct it from generator/request metadata.

    Implementations must enforce tenant isolation, independent verifier write access,
    current revocation and bounded lookup latency. Returning None means unverified.
    """

    def get_verified(
        self,
        tenant_id: str,
        decision_id: str,
        evidence_id: str,
    ) -> EvidenceVerification | None: ...


class InMemoryEvidenceRegistry:
    """Immutable snapshot adapter for development/tests, not a production verifier."""

    def __init__(self, records: Iterable[EvidenceVerification] = ()):
        self._records: dict[tuple[str, str, str], EvidenceVerification] = {}
        for record in records:
            key = (record.tenant_id, record.decision_id, record.evidence_id)
            if key in self._records:
                raise ValueError("DUPLICATE_EVIDENCE_VERIFICATION")
            self._records[key] = record

    def get_verified(
        self,
        tenant_id: str,
        decision_id: str,
        evidence_id: str,
    ) -> EvidenceVerification | None:
        return self._records.get((tenant_id, decision_id, evidence_id))
