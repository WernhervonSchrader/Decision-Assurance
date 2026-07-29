from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from .contracts import PolicyContext, VerificationReport, VerificationStatus

Clock = Callable[[], datetime]


class CompilationRejected(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DecisionFileCompiler:
    """The sole boundary permitted to translate verified intake into a Decision File."""

    def __init__(self, *, clock: Clock = _utc_now):
        self._clock = clock

    def compile(
        self,
        report: VerificationReport,
        *,
        policy: PolicyContext,
        actor_id: str,
    ) -> dict[str, Any]:
        if not report.ready or report.unresolved_requirement_refs:
            raise CompilationRejected("NEEDS_CONFIRMATION")
        verified = tuple(
            candidate
            for candidate in report.candidates
            if candidate.verification_status
            in {VerificationStatus.VERIFIED, VerificationStatus.HUMAN_CONFIRMED}
        )
        if not verified:
            raise CompilationRejected("NEEDS_CONFIRMATION")

        timestamp = self._clock().astimezone(timezone.utc).isoformat()
        decision_id = f"{report.intake_id}-decision"
        actor = {"id": actor_id, "role": "GENERATOR", "kind": "SERVICE"}
        claims = [
            {
                "id": f"claim-{index}",
                "statement": f"{candidate.fact_type.value} = {candidate.normalized_value}",
                "mandatory_evidence": True,
            }
            for index, candidate in enumerate(verified, 1)
        ]
        evidence = [
            {
                "id": candidate.fact_id,
                "claim_refs": [f"claim-{index}"],
                "source_ref": (
                    f"{candidate.source.source_id}:{candidate.source.start}-{candidate.source.end}"
                ),
                "status": "VERIFIED",
                "content_hash": candidate.source.content_hash,
            }
            for index, candidate in enumerate(verified, 1)
        ]
        audit_payload = {
            "intake_id": report.intake_id,
            "used_fact_refs": [candidate.fact_id for candidate in verified],
        }
        payload_hash = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(audit_payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        )
        return {
            "schema_version": "0.1.0",
            "decision_id": decision_id,
            "title": f"Compiled intake {report.intake_id}",
            "description": "Decision File compiled exclusively from verified intake facts.",
            "use_case": "controlled-real-world-intake",
            "status": "DRAFT",
            "assurance_level": "STANDARD",
            "created_at": timestamp,
            "updated_at": timestamp,
            "created_by": actor,
            "current_owner": actor,
            "claims": claims,
            "evidence": evidence,
            "assumptions": [],
            "constraints": [],
            "policies": [
                {"id": policy.policy_id, "version": policy.policy_version, "requires_review": False}
            ],
            "risks": [],
            "conflicts": [],
            "validation_results": [],
            "review_requirements": [],
            "approvals": [],
            "decision_outcome": None,
            "outcome_reasons": [],
            "audit_events": [
                {
                    "event_id": f"{decision_id}:audit:1",
                    "event_type": "intake.compiled",
                    "occurred_at": timestamp,
                    "actor": actor,
                    "from_status": None,
                    "to_status": "DRAFT",
                    "reason_codes": ["VERIFIED_INTAKE_COMPILED"],
                    "payload_hash": payload_hash,
                    "previous_event_hash": None,
                }
            ],
        }
