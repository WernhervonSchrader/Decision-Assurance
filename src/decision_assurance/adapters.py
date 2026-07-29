from __future__ import annotations

from typing import Any


def normalize(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize either a DATS case or a native assessment request."""
    if "input" in payload and isinstance(payload["input"], dict):
        data = payload["input"]
        return {
            "decision_id": payload.get("id", "unidentified-decision"),
            "claim": data.get("claim", ""),
            "evidence": data.get("evidence", []),
            "constraints": data.get("constraints", []),
            "policies": data.get("policies", []),
            "actors": data.get("actors", {}),
            "risk": data.get("risk", {}),
            "conflicts": data.get("conflicts", []),
            "mandatory_evidence_missing": data.get("mandatory_evidence_missing", False),
            "policy_version": payload.get("policy_version", "dats-0.1.0"),
        }

    normalized = dict(payload)
    normalized.setdefault("decision_id", "unidentified-decision")
    normalized.setdefault("evidence", [])
    normalized.setdefault("constraints", [])
    normalized.setdefault("policies", [])
    normalized.setdefault("actors", {})
    normalized.setdefault("risk", {})
    normalized.setdefault("conflicts", [])
    normalized.setdefault("mandatory_evidence_missing", False)
    normalized.setdefault("policy_version", "unspecified")
    return normalized
