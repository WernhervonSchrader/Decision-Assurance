from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from decision_assurance.release_verification import MANDATORY_GATES

GATE_JOBS = {
    "unit-quality": "verify",
    "dependency-audit": "verify",
    "secret-scan": "secret-scan",
    "oidc-validation": "verify",
    "postgresql-migrations": "postgresql",
    "tenant-isolation": "postgresql",
    "database-roles": "postgresql",
    "worker-recovery": "verify",
    "production-configuration": "verify",
    "observability-health": "verify",
    "container-scan": "container-security",
    "restore-verification": "restore-verification",
    "controlled-pilot-e2e": "postgresql",
}

GATE_STEPS = {
    "unit-quality": (
        "Ruff format",
        "Ruff lint",
        "Mypy strict",
        "Non-PostgreSQL test suite",
        "Gold benchmark",
        "Intake benchmark",
        "Bandit static analysis",
        "Build Python packages",
        "OpenAPI v0.4 contract",
        "OpenAPI v0.5 contract",
    ),
    "dependency-audit": ("Dependency vulnerability audit",),
    "secret-scan": ("Gitleaks secret scan",),
    "oidc-validation": ("Non-PostgreSQL test suite",),
    "postgresql-migrations": ("PostgreSQL integration and E2E",),
    "tenant-isolation": ("PostgreSQL integration and E2E",),
    "database-roles": ("PostgreSQL integration and E2E",),
    "worker-recovery": ("Non-PostgreSQL test suite",),
    "production-configuration": ("Non-PostgreSQL test suite",),
    "observability-health": ("Non-PostgreSQL test suite",),
    "container-scan": (
        "Scan API image for critical vulnerabilities",
        "Scan Worker image for critical vulnerabilities",
        "Scan MCP image for critical vulnerabilities",
    ),
    "restore-verification": ("Backup and restore into a fresh database",),
    "controlled-pilot-e2e": ("PostgreSQL integration and E2E",),
}


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("INVALID_CI_EVIDENCE_JSON")
    return value


def _job_is_successful(job: dict[str, Any], required_steps: tuple[str, ...]) -> bool:
    if job.get("status") != "completed" or job.get("conclusion") != "success":
        return False
    steps = job.get("steps")
    if not isinstance(steps, list) or not steps:
        return False
    by_name = {
        step.get("name"): step.get("conclusion")
        for step in steps
        if isinstance(step, dict) and isinstance(step.get("name"), str)
    }
    return all(by_name.get(name) == "success" for name in required_steps)


def _verify_checksums(artifact_root: Path, checksum_path: Path) -> tuple[bool, tuple[str, ...]]:
    root = artifact_root.resolve(strict=True)
    lines = checksum_path.read_text(encoding="utf-8").splitlines()
    references: list[str] = []
    if not lines:
        return False, ()
    for line in lines:
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            return False, ()
        expected, relative = parts
        candidate = (root / relative).resolve()
        if root not in candidate.parents or not candidate.is_file():
            return False, ()
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if actual != expected:
            return False, ()
        references.append(f"sha256:{actual}:{relative}")
    return True, tuple(references)


def compute_gate_input(
    *,
    workflow_run: dict[str, Any],
    workflow_jobs: dict[str, Any],
    artifact_root: Path,
    checksum_path: Path,
    expected_commit: str,
    expected_repository: str,
) -> list[dict[str, Any]]:
    if set(GATE_JOBS).union({"artifact-integrity"}) != set(MANDATORY_GATES) or set(
        GATE_STEPS
    ) != set(GATE_JOBS):
        raise RuntimeError("CI_RELEASE_GATE_MAPPING_INCOMPLETE")
    repository = workflow_run.get("repository")
    actual_repository = repository.get("full_name") if isinstance(repository, dict) else None
    run_id = workflow_run.get("id")
    run_bound = (
        actual_repository == expected_repository
        and workflow_run.get("head_sha") == expected_commit
        and isinstance(run_id, int)
        and run_id > 0
    )
    raw_jobs = workflow_jobs.get("jobs")
    job_records = (
        [item for item in raw_jobs if isinstance(item, dict) and isinstance(item.get("name"), str)]
        if isinstance(raw_jobs, list)
        else []
    )
    duplicate_names = {
        item["name"]
        for item in job_records
        if sum(other["name"] == item["name"] for other in job_records) > 1
    }
    jobs = {item["name"]: item for item in job_records if item["name"] not in duplicate_names}
    checksum_valid, artifact_refs = _verify_checksums(artifact_root, checksum_path)
    gates: list[dict[str, Any]] = []
    for gate_id in MANDATORY_GATES:
        if gate_id == "artifact-integrity":
            passed = run_bound and checksum_valid and bool(artifact_refs)
            refs = list(artifact_refs) if passed else ["release-evidence:checksum-validation"]
            reason = [] if passed else ["ARTIFACT_INTEGRITY_NOT_VERIFIED"]
        else:
            job_name = GATE_JOBS[gate_id]
            job = jobs.get(job_name)
            passed = run_bound and job is not None and _job_is_successful(job, GATE_STEPS[gate_id])
            job_id = job.get("id") if job is not None else "missing"
            refs = [
                f"github-actions://{expected_repository}/runs/{run_id}/jobs/{job_id}"
                f"?commit={expected_commit}#{gate_id}"
            ]
            reason = [] if passed else ["CI_JOB_EVIDENCE_NOT_VERIFIED"]
        gates.append(
            {
                "gate_id": gate_id,
                "status": "PASS" if passed else "BLOCK",
                "reason_codes": reason,
                "evidence_refs": refs,
            }
        )
    return gates


def write_gate_input(
    output: Path,
    *,
    workflow_run_path: Path,
    workflow_jobs_path: Path,
    artifact_root: Path,
    checksum_path: Path,
    expected_commit: str,
    expected_repository: str,
) -> None:
    gates = compute_gate_input(
        workflow_run=_load_object(workflow_run_path),
        workflow_jobs=_load_object(workflow_jobs_path),
        artifact_root=artifact_root,
        checksum_path=checksum_path,
        expected_commit=expected_commit,
        expected_repository=expected_repository,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(gates, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--workflow-run", type=Path, required=True)
    parser.add_argument("--workflow-jobs", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    write_gate_input(
        args.output,
        workflow_run_path=args.workflow_run,
        workflow_jobs_path=args.workflow_jobs,
        artifact_root=args.artifact_root,
        checksum_path=args.checksums,
        expected_commit=args.commit_sha,
        expected_repository=args.repository,
    )


if __name__ == "__main__":
    main()
