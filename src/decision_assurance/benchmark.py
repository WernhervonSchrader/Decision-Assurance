from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .engine import DecisionAssuranceEngine
from .transitions import TransitionPolicy, TransitionRejected


def run_benchmark(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = [_run_case(case, manifest_path.parent) for case in manifest["scenarios"]]
    return {
        "schema_version": manifest["schema_version"],
        "total": len(results),
        "passed": sum(result["passed"] for result in results),
        "failed": sum(not result["passed"] for result in results),
        "results": results,
    }


def _run_case(case: dict[str, Any], root: Path) -> dict[str, Any]:
    if case["kind"] == "transition":
        fixture = _transition_fixture()
        fixture["status"] = case["source"]
        try:
            updated = TransitionPolicy().transition(
                fixture, case["target"], {"id": "validator", "role": "VALIDATOR", "kind": "HUMAN"}
            )
            actual_outcome, reasons, status, events = (
                "AUTHORIZED",
                [],
                updated["status"],
                ["status.transitioned"],
            )
        except TransitionRejected as error:
            actual_outcome, reasons, status, events = (
                "REJECTED",
                error.reason_codes,
                fixture["status"],
                [],
            )
    else:
        payload = case.get("input")
        if payload is None:
            payload = json.loads(
                (root / case["scenario_ref"]).resolve().read_text(encoding="utf-8")
            )
        result = DecisionAssuranceEngine().assess(payload)
        actual_outcome = result.outcome.value
        reasons = list(result.reason_codes)
        status = "BLOCKED" if actual_outcome == "BLOCK" else "REVIEW"
        events = list(dict.fromkeys(event["event_type"] for event in result.audit_events))
    expected = {
        "outcome": case["expected_outcome"],
        "reasons": case["expected_reasons"],
        "status": case["expected_status"],
        "audit_events": case["expected_audit_events"],
    }
    actual = {
        "outcome": actual_outcome,
        "reasons": reasons,
        "status": status,
        "audit_events": events,
    }
    return {"id": case["id"], "passed": actual == expected, "expected": expected, "actual": actual}


def _transition_fixture() -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "decision_id": "BENCHMARK-TRANSITION",
        "title": "Transition benchmark fixture",
        "description": "Self-contained deterministic transition input.",
        "use_case": "benchmark",
        "status": "DRAFT",
        "assurance_level": "BASIC",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "created_by": {"id": "generator", "role": "GENERATOR", "kind": "AGENT"},
        "current_owner": {"id": "owner", "role": "OWNER", "kind": "HUMAN"},
        "claims": [{"id": "C-1", "statement": "Fixture claim", "mandatory_evidence": False}],
        "evidence": [],
        "assumptions": [],
        "constraints": [],
        "policies": [],
        "risks": [],
        "conflicts": [],
        "validation_results": [],
        "review_requirements": [],
        "approvals": [],
        "decision_outcome": None,
        "outcome_reasons": [],
        "audit_events": [],
    }
