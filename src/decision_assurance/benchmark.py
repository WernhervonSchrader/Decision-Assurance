from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .engine import DecisionAssuranceEngine
from .transitions import TransitionPolicy, TransitionRejected

DATS_CATALOG_VERSION = "decision-assurance.dats-catalog/1.0"
DATS_CASE_VERSION = "decision-assurance.dats-case/1.0"


def run_benchmark(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") == DATS_CATALOG_VERSION:
        return _run_dats_catalog(manifest, manifest_path)
    results = [_run_case(case, manifest_path.parent) for case in manifest["scenarios"]]
    return {
        "schema_version": manifest["schema_version"],
        "total": len(results),
        "passed": sum(result["passed"] for result in results),
        "failed": sum(not result["passed"] for result in results),
        "results": results,
    }


def _run_dats_catalog(catalog: dict[str, Any], catalog_path: Path) -> dict[str, Any]:
    root = catalog_path.parent.resolve()
    schemas = root.parent / "schemas"
    _validate_json(catalog, schemas / "dats-catalog.schema.json", "catalog")
    if catalog["case_count"] != len(catalog["cases"]):
        raise ValueError("DATS_CASE_COUNT_MISMATCH")
    ids = [item["id"] for item in catalog["cases"]]
    if len(ids) != len(set(ids)):
        raise ValueError("DATS_DUPLICATE_CASE_ID")

    results: list[dict[str, Any]] = []
    for item in catalog["cases"]:
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("DATS_CASE_PATH_OUTSIDE_DATASET")
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError("DATS_CASE_PATH_OUTSIDE_DATASET")
        case = json.loads(path.read_text(encoding="utf-8"))
        _validate_json(case, schemas / "dats-case.schema.json", item["id"])
        if case["schema_version"] != DATS_CASE_VERSION or case["id"] != item["id"]:
            raise ValueError("DATS_CASE_ID_OR_VERSION_MISMATCH")
        results.append(_run_dats_case(case))

    return {
        "schema_version": catalog["schema_version"],
        "dataset_id": catalog["dataset_id"],
        "dataset_version": catalog["dataset_version"],
        "total": len(results),
        "passed": sum(result["passed"] for result in results),
        "failed": sum(not result["passed"] for result in results),
        "results": results,
    }


def _validate_json(value: dict[str, Any], schema_path: Path, subject: str) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value), key=lambda item: list(item.path)
    )
    if errors:
        raise ValueError(f"DATS_SCHEMA_INVALID:{subject}:{errors[0].message}")


def _run_dats_case(case: dict[str, Any]) -> dict[str, Any]:
    result = DecisionAssuranceEngine().assess(case["task"]["input"])
    gate_decision = {
        "PASS": "PASS",  # nosec B105 - governance state labels, not credentials
        "BLOCK": "FAIL",
        "REVIEW": "REQUIRES_HUMAN_REVIEW",
    }[result.outcome.value]
    actual = {
        "gate_decision": gate_decision,
        "engine_outcome": result.outcome.value,
        "human_review": result.human_review,
        "reason_codes": list(result.reason_codes),
        "finding_reason_codes": [finding.reason_code for finding in result.findings],
        "audit_event_types": list(
            dict.fromkeys(event["event_type"] for event in result.audit_events)
        ),
    }
    expected = case["expected_result"]
    return {"id": case["id"], "passed": actual == expected, "expected": expected, "actual": actual}


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
        "schema_version": "0.2.0",
        "decision_id": "BENCHMARK-TRANSITION",
        "title": "Transition benchmark fixture",
        "description": "Self-contained deterministic transition input.",
        "use_case": "benchmark",
        "status": "DRAFT",
        "assurance_level": "BASIC",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "created_by": {"id": "generator", "role": "GENERATOR", "kind": "AGENT"},
        "requested_by": {"id": "requester", "role": "OWNER", "kind": "HUMAN"},
        "current_owner": {"id": "owner", "role": "OWNER", "kind": "HUMAN"},
        "canonical_action": None,
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
