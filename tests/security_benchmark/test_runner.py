import copy
import json
from pathlib import Path

import pytest

from decision_assurance.security_benchmark.cases import own_cases
from decision_assurance.security_benchmark.contracts import validate_case
from decision_assurance.security_benchmark.metrics import calculate_metrics
from decision_assurance.security_benchmark.runner import compare_reports, run_cases


def test_synthetic_cases_are_valid_diverse_and_all_families_covered() -> None:
    cases = own_cases("standard")
    assert len(cases) >= 100
    assert len({c["test_id"] for c in cases}) == len(cases)
    assert {c["tenant_id"] for c in cases} == {"tenant-a", "tenant-b"}
    assert {c["locale"] for c in cases} == {"de", "en"}
    for case in cases:
        validate_case(case)
    assert {c["family"] for c in cases} >= {f"B{i}" for i in range(1, 7)} | {
        f"C{i}" for i in range(1, 8)
    }
    invalid = dict(cases[0], unexpected="bad")
    with pytest.raises(ValueError, match="CASE_INVALID"):
        validate_case(invalid)


def test_real_target_gaps_are_failed_observations_not_green_mock_results(tmp_path: Path) -> None:
    report = run_cases(own_cases("smoke"), tmp_path)
    b1 = next(r for r in report["results"] if r["family"] == "B1")
    assert b1["governance_outcome"] == "PASS"
    assert b1["status"] == "SECURITY_FAILURE"
    assert b1["executed"] is None
    assert any(r["family"] == "B4" and r["status"] == "PASS" for r in report["results"])
    assert any(r["family"] == "B0" and r["governance_outcome"] == "PASS" for r in report["results"])
    assert all(
        r["execution_scope"] == "simulation_only" for r in report["results"] if r["layer"] == "C"
    )
    assert report["metrics"]["attack_success_rate"]["value"] is None
    assert "body" not in json.dumps(report)


@pytest.mark.parametrize(
    "field,value",
    [
        ("governance_outcome", "PASS"),
        ("audit_complete", False),
        ("evidence_integrity", False),
        ("freshness_valid", False),
        ("status", "INFRASTRUCTURE_ERROR"),
    ],
)
def test_regression_detects_independent_safety_signals(
    tmp_path: Path, field: str, value: object
) -> None:
    baseline = run_cases(own_cases("smoke"), tmp_path)
    changed = copy.deepcopy(baseline)
    target = next(
        r
        for r in changed["results"]
        if r["family"] == ("C0" if field == "freshness_valid" else "C1")
    )
    target[field] = value
    assert compare_reports(baseline, changed)["regressions"]


def test_metric_denominators_and_exclusions() -> None:
    empty = calculate_metrics([])
    assert all(x["value"] is None for x in empty.values())
    row = {
        "layer": "A",
        "status": "INCONCLUSIVE",
        "attack_success": None,
        "attack_ground_truth": None,
        "detected": None,
        "unauthorized": None,
        "governance_outcome": None,
        "executed": None,
        "audit_complete": None,
        "evidence_integrity": None,
        "freshness_valid": None,
    }
    metrics = calculate_metrics([row])
    assert metrics["attack_success_rate"]["denominator"] == 0
    assert metrics["false_positive_rate"]["denominator"] == 0


def test_resume_checks_identity_and_results_prefix(tmp_path: Path) -> None:
    cases = own_cases("smoke")
    checkpoint = tmp_path / "checkpoint.jsonl"
    a = run_cases(cases, tmp_path, checkpoint=checkpoint)
    resumed = run_cases(cases, tmp_path, checkpoint=checkpoint)
    assert resumed["checkpoint_reused_cases"] == len(cases)
    processing = {"checkpoint_reused_cases", "fresh_case_measurements", "fresh_security_components"}
    assert {k: v for k, v in a.items() if k not in processing} == {
        k: v for k, v in resumed.items() if k not in processing
    }
    changed = copy.deepcopy(cases)
    changed[0]["variant"] += 1
    with pytest.raises(ValueError, match="CHECKPOINT"):
        run_cases(changed, tmp_path, checkpoint=checkpoint)
    lines = checkpoint.read_text().splitlines()
    lines[-1] = lines[-1].replace("simulation_only", "production")
    checkpoint.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="CHECKPOINT"):
        run_cases(cases, tmp_path, checkpoint=checkpoint)
