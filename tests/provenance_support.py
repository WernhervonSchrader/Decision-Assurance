"""Explicit synthetic independent-verifier setup for legacy positive journeys.

Never used by application code, request parsing, benchmarks or negative B2 tests.
Fixtures model provisioned server authority; they are not real source authentication.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from decision_assurance.provenance.evidence import (
    EvidenceVerification,
    InMemoryEvidenceRegistry,
    evidence_binding,
)


def verified_fixture_registry(
    document: dict[str, Any],
    tenant_id: str,
    *,
    replace_placeholder_hashes: bool = True,
) -> InMemoryEvidenceRegistry:
    now = datetime.now(timezone.utc)
    # Legacy example has a placeholder, not a real hash. Supply an explicit synthetic hash.
    if replace_placeholder_hashes:
        for evidence in document["evidence"]:
            evidence["content_hash"] = "sha256:" + "a" * 64
    data = {
        "decision_id": document["decision_id"],
        "claims": document["claims"],
        "policies": document["policies"],
        "policy_version": ",".join(p["version"] for p in document["policies"]) or "none",
    }
    return InMemoryEvidenceRegistry(
        EvidenceVerification(
            verification_id=f"synthetic-independent:{e['id']}",
            tenant_id=tenant_id,
            decision_id=document["decision_id"],
            evidence_id=e["id"],
            generator_id=document["created_by"]["id"],
            validator_id="synthetic-independent-verifier",
            binding_hash=evidence_binding(data, e),
            verified_at=now - timedelta(minutes=1),
            valid_until=now + timedelta(minutes=5),
        )
        for e in document["evidence"]
    )
