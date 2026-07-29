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
        fixture = json.loads((Path(__file__).parents[2] / "examples" / "decision-cases" / "low-risk-pass.json").read_text(encoding="utf-8"))
        fixture["status"] = case["source"]
        try:
            updated = TransitionPolicy().transition(fixture, case["target"], {"id":"validator","role":"VALIDATOR","kind":"HUMAN"})
            actual_outcome, reasons, status, events = "AUTHORIZED", [], updated["status"], ["status.transitioned"]
        except TransitionRejected as error:
            actual_outcome, reasons, status, events = "REJECTED", error.reason_codes, fixture["status"], []
    else:
        payload = case.get("input")
        if payload is None:
            payload = json.loads((root / case["scenario_ref"]).resolve().read_text(encoding="utf-8"))
        result = DecisionAssuranceEngine().assess(payload)
        actual_outcome = result.outcome.value
        reasons = list(result.reason_codes)
        status = "BLOCKED" if actual_outcome == "BLOCK" else "REVIEW"
        events = list(dict.fromkeys(event["event_type"] for event in result.audit_events))
    expected = {
        "outcome": case["expected_outcome"], "reasons": case["expected_reasons"],
        "status": case["expected_status"], "audit_events": case["expected_audit_events"]
    }
    actual = {"outcome": actual_outcome, "reasons": reasons, "status": status, "audit_events": events}
    return {"id": case["id"], "passed": actual == expected, "expected": expected, "actual": actual}

