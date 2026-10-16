from __future__ import annotations

import gc
import hashlib
import json
import sqlite3
import sys
from collections.abc import Iterable
from functools import lru_cache
from importlib.metadata import version
from itertools import zip_longest
from pathlib import Path
from typing import Any

from .adapters import observation, run_execution, run_governance, run_source
from .contracts import digest, safe_child, validate_case
from .metrics import calculate_metrics

SIGNALS = (
    "case_sha256",
    "status",
    "component_executed",
    "governance_outcome",
    "governance_escape",
    "policy_gap",
    "finding_scope",
    "finding_severity",
    "audit_scope",
    "audit_sha256",
    "original_result",
    "original_attack_success",
    "original_tool_proposed",
    "authorization_result",
    "lifecycle_state",
    "executed",
    "audit_complete",
    "audit_event_types",
    "evidence_integrity",
    "freshness_valid",
    "execution_scope",
    "attack_success",
    "detected",
    "tool_proposed",
    "reason_codes",
)


@lru_cache(maxsize=1)
def implementation_fingerprint() -> str:
    root = Path(__file__).parents[1]
    paths = (
        list(root.rglob("*.py"))
        + list((root / "schemas").rglob("*.json"))
        + [Path(__file__).with_name("locales.json")]
    )
    return digest(
        {
            p.relative_to(root).as_posix(): hashlib.sha256(
                p.read_text(encoding="utf8").encode()
            ).hexdigest()
            for p in sorted(paths)
        }
    )


@lru_cache(maxsize=1)
def runtime_versions() -> dict[str, Any]:
    return {
        "python": list(sys.version_info[:3]),
        "packages": {
            name: version(name)
            for name in (
                "fastapi",
                "starlette",
                "httpx",
                "jsonschema",
                "mcp",
                "cryptography",
                "psycopg",
            )
        },
    }


def run_cases(
    cases: Iterable[dict[str, Any]],
    workspace: Path,
    *,
    payload_root: Path | None = None,
    checkpoint: Path | None = None,
    profile: str = "custom",
    seed: int = 42,
) -> dict[str, Any]:
    workspace.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    ids: set[str] = set()
    saved: list[dict[str, Any]] = []
    identity = {
        "benchmark_version": "0.1",
        "profile": profile,
        "seed": seed,
        "implementation_sha256": implementation_fingerprint(),
        "runtime_versions": runtime_versions(),
    }
    if checkpoint and checkpoint.exists():
        for line in checkpoint.read_text(encoding="utf8").splitlines():
            try:
                entry = json.loads(line)
                if (
                    entry["previous_hash"] != (saved[-1]["hash"] if saved else None)
                    or entry["identity"] != identity
                    or entry["hash"]
                    != digest(
                        {
                            "identity": identity,
                            "result": entry["result"],
                            "previous_hash": saved[-1]["hash"] if saved else None,
                        }
                    )
                ):
                    raise ValueError("CHECKPOINT_INVALID")
                saved.append(entry)
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError("CHECKPOINT_INVALID") from error
    reused_count = len(saved)
    for index, case in enumerate(cases):
        validate_case(case)
        if case["test_id"] in ids:
            raise ValueError("DUPLICATE_TEST_ID")
        ids.add(case["test_id"])
        if index < len(saved):
            result = saved[index]["result"]
            if result["case_sha256"] != digest(case):
                raise ValueError("CHECKPOINT_CASE_MISMATCH")
            if case["layer"] == "A":
                if payload_root is None:
                    raise ValueError("CHECKPOINT_PAYLOAD_ROOT_REQUIRED")
                run_source(
                    case, payload_root
                )  # Reverify raw bytes; cached observations grant no trust.
        else:
            try:
                if case["layer"] == "A":
                    if payload_root is None:
                        raise ValueError("PAYLOAD_ROOT_REQUIRED")
                    result = run_source(case, payload_root)
                elif case["layer"] == "B":
                    # One isolated database per execution, including reruns.
                    from tempfile import TemporaryDirectory

                    with TemporaryDirectory(prefix="security-case-", dir=workspace) as directory:
                        try:
                            result = run_governance(case, Path(directory))
                        finally:
                            # The reference repository uses transaction context managers, whose
                            # connections close on collection. Release them before Windows cleanup.
                            gc.collect()
                else:
                    result = run_execution(case)
            except ValueError:
                result = observation(case)
                result.update(status="TEST_ERROR", reason_codes=["INVALID_FIXTURE_OR_CONTRACT"])
            except (OSError, RuntimeError, KeyError, sqlite3.DatabaseError):
                result = observation(case)
                result.update(
                    status="INFRASTRUCTURE_ERROR", reason_codes=["REQUIRED_COMPONENT_FAILED"]
                )
            if checkpoint:
                checkpoint.parent.mkdir(parents=True, exist_ok=True)
                previous = saved[-1]["hash"] if saved else None
                entry = {"identity": identity, "result": result, "previous_hash": previous}
                entry["hash"] = digest(entry)
                with checkpoint.open("a", encoding="utf8") as stream:
                    stream.write(json.dumps(entry, sort_keys=True) + "\n")
                    stream.flush()
                saved.append(entry)
        results.append(result)
    if len(saved) > len(results):
        raise ValueError("CHECKPOINT_CASE_SET_SHORTENED")
    counts = {
        status: sum(r["status"] == status for r in results)
        for status in (
            "PASS",
            "SECURITY_FAILURE",
            "INCONCLUSIVE",
            "SKIPPED",
            "TEST_ERROR",
            "INFRASTRUCTURE_ERROR",
        )
    }
    return {
        **identity,
        "schema_version": "0.1",
        "execution_mode": "simulation",
        "case_set_sha256": digest([r["case_sha256"] for r in results]),
        "total_cases": len(results),
        "checkpoint_reused_cases": reused_count,
        "fresh_case_measurements": len(results) - reused_count,
        "fresh_security_components": sum(
            bool(r["component_executed"]) for r in results[reused_count:]
        ),
        "evaluated": counts["PASS"] + counts["SECURITY_FAILURE"],
        "counts": counts,
        "metrics": calculate_metrics(results),
        "results": results,
        "original_observations": {
            "evaluable": sum(isinstance(r["original_attack_success"], bool) for r in results),
            "successful_tool_objectives": sum(
                r["original_attack_success"] is True for r in results
            ),
            "tool_proposals": sum(r["original_tool_proposed"] is True for r in results),
            "scope": "Microsoft source observations, not fresh DA measurements or actual mail delivery.",
        },
        "critical_findings": [
            r["test_id"]
            for r in results
            if r["status"] == "SECURITY_FAILURE" and r.get("finding_severity") == "CRITICAL"
        ],
        "measurement_counts": {
            "attacks_detected": sum(
                r["layer"] == "A" and r["attack_ground_truth"] is True and r["detected"] is True
                for r in results
            ),
            "attacks_successful": sum(
                r["layer"] == "A" and r["attack_success"] is True for r in results
            ),
            "attacks_defended": sum(
                r["layer"] == "A" and r["attack_success"] is False for r in results
            ),
            "agent_measurements_unavailable": sum(
                r["layer"] == "A" and r["attack_success"] is None for r in results
            ),
            "false_positives": sum(
                r["layer"] == "A" and r["attack_ground_truth"] is False and r["detected"] is True
                for r in results
            ),
        },
        "known_limitations": [
            "MODEL_ADAPTER_DISABLED",
            "NO_PRODUCTION_EXECUTION_GATEWAY",
            "STATIC_TEST_IDENTITY_NOT_PRODUCTION_OIDC",
        ],
        "regression_findings": [],
    }


def compare_reports(baseline: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    if baseline.get("result_stream") or report.get("result_stream"):
        raise ValueError("STREAM_COMPARISON_REQUIRES_COMPLETE_RESULTS")
    for key in (
        "schema_version",
        "benchmark_version",
        "profile",
        "seed",
        "execution_mode",
        "case_set_sha256",
        "dataset_revision",
        "dataset_checksum",
    ):
        if baseline.get(key) != report.get(key):
            raise ValueError("REGRESSION_RUN_IDENTITY_MISMATCH")
    prior = {r["test_id"]: r for r in baseline["results"]}
    current = {r["test_id"]: r for r in report["results"]}
    if len(prior) != len(baseline["results"]) or len(current) != len(report["results"]):
        raise ValueError("REGRESSION_DUPLICATE_ID")
    changes: list[dict[str, Any]] = []
    for test_id, expected in prior.items():
        actual = current.get(test_id)
        if actual is None:
            changes.append({"test_id": test_id, "kind": "MISSING_CASE"})
            continue
        if actual["status"] in {"TEST_ERROR", "INFRASTRUCTURE_ERROR", "SKIPPED"}:
            changes.append({"test_id": test_id, "kind": "REQUIRED_COMPONENT_NOT_EVALUATED"})
        for field in SIGNALS:
            if expected.get(field) != actual.get(field):
                changes.append(
                    {
                        "test_id": test_id,
                        "kind": "SIGNAL_CHANGED",
                        "field": field,
                        "before": expected.get(field),
                        "after": actual.get(field),
                    }
                )
    for test_id in current.keys() - prior.keys():
        changes.append({"test_id": test_id, "kind": "UNREVIEWED_NEW_CASE"})
    return {
        "regressions": changes,
        "known_security_failures": report["counts"]["SECURITY_FAILURE"],
        "security_pass": report["counts"]["SECURITY_FAILURE"] == 0,
        "regression_pass": not changes,
    }


def compare_stream_reports(
    baseline: dict[str, Any], report: dict[str, Any], baseline_root: Path, report_root: Path
) -> dict[str, Any]:
    """Compare every complete streamed result; never compare just management samples."""
    from .dataset import verify_file

    for key in (
        "schema_version",
        "benchmark_version",
        "profile",
        "seed",
        "execution_mode",
        "case_set_sha256",
        "dataset_revision",
        "dataset_checksum",
        "total_cases",
    ):
        if baseline.get(key) != report.get(key):
            raise ValueError("REGRESSION_RUN_IDENTITY_MISMATCH")
    paths = []
    for summary, root in ((baseline, baseline_root), (report, report_root)):
        descriptor = summary["result_stream"]
        path = safe_child(root, descriptor["path"])
        verify_file(path, descriptor["sha256"], descriptor["size"])
        paths.append(path)
    changes: list[dict[str, Any]] = []
    count = 0
    seen = 0
    with paths[0].open(encoding="utf8") as first, paths[1].open(encoding="utf8") as second:
        for prior_line, current_line in zip_longest(first, second):
            if prior_line is None or current_line is None:
                raise ValueError("REGRESSION_STREAM_LENGTH_MISMATCH")
            before, after = json.loads(prior_line), json.loads(current_line)
            if (
                before["test_id"] != after["test_id"]
                or before["case_sha256"] != after["case_sha256"]
            ):
                raise ValueError("REGRESSION_STREAM_CASE_MISMATCH")
            seen += 1
            if after["status"] in {"TEST_ERROR", "INFRASTRUCTURE_ERROR", "SKIPPED"}:
                count += 1
                if len(changes) < 1000:
                    changes.append(
                        {"test_id": after["test_id"], "kind": "REQUIRED_COMPONENT_NOT_EVALUATED"}
                    )
            for field in SIGNALS:
                if before.get(field) != after.get(field):
                    count += 1
                    if len(changes) < 1000:
                        changes.append(
                            {
                                "test_id": after["test_id"],
                                "kind": "SIGNAL_CHANGED",
                                "field": field,
                                "before": before.get(field),
                                "after": after.get(field),
                            }
                        )
    if seen != report["total_cases"]:
        raise ValueError("REGRESSION_STREAM_COUNT_MISMATCH")
    return {
        "regressions": changes,
        "regression_count": count,
        "details_truncated": count > len(changes),
        "known_security_failures": report["counts"]["SECURITY_FAILURE"],
        "security_pass": report["counts"]["SECURITY_FAILURE"] == 0,
        "regression_pass": count == 0,
    }
