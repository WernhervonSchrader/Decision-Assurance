from __future__ import annotations

from pathlib import Path

from scripts.release.checksums import create_checksum_manifest
from scripts.release.ci_gate_input import GATE_JOBS, GATE_STEPS, compute_gate_input

COMMIT = "a" * 40
REPOSITORY = "WernhervonSchrader/Decision-Assurance"


def _workflow_run(commit: str = COMMIT) -> dict[str, object]:
    return {
        "id": 12345,
        "head_sha": commit,
        "repository": {"full_name": REPOSITORY},
    }


def _workflow_jobs(*, failed_job: str | None = None) -> dict[str, object]:
    jobs = []
    for index, name in enumerate(sorted(set(GATE_JOBS.values())), 1):
        conclusion = "failure" if name == failed_job else "success"
        required_steps = sorted(
            {
                step
                for gate_id, job_name in GATE_JOBS.items()
                if job_name == name
                for step in GATE_STEPS[gate_id]
            }
        )
        jobs.append(
            {
                "id": index,
                "name": name,
                "status": "completed",
                "conclusion": conclusion,
                "steps": [
                    {
                        "name": step,
                        "status": "completed",
                        "conclusion": conclusion,
                    }
                    for step in required_steps
                ],
            }
        )
    return {"jobs": jobs}


def _artifacts(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "package.whl").write_bytes(b"immutable-package")
    (root / "restore-verification.json").write_text(
        '{"commit_sha":"' + COMMIT + '","status":"PASS"}',
        encoding="utf-8",
    )
    checksums = tmp_path / "SHA256SUMS"
    create_checksum_manifest(root, checksums)
    return root, checksums


def _compute(tmp_path: Path, **overrides):  # type: ignore[no-untyped-def]
    root, checksums = _artifacts(tmp_path)
    values = {
        "workflow_run": _workflow_run(),
        "workflow_jobs": _workflow_jobs(),
        "artifact_root": root,
        "checksum_path": checksums,
        "expected_commit": COMMIT,
        "expected_repository": REPOSITORY,
    }
    values.update(overrides)
    return compute_gate_input(**values)


def test_release_gates_are_derived_from_commit_bound_jobs_and_artifacts(tmp_path: Path) -> None:
    gates = _compute(tmp_path)

    assert gates and {item["status"] for item in gates} == {"PASS"}
    assert all(COMMIT in reference for item in gates[:-1] for reference in item["evidence_refs"])
    assert all(reference.startswith("sha256:") for reference in gates[-1]["evidence_refs"])


def test_commit_mismatch_blocks_every_gate(tmp_path: Path) -> None:
    gates = _compute(tmp_path, workflow_run=_workflow_run("b" * 40))

    assert {item["status"] for item in gates} == {"BLOCK"}


def test_failed_source_job_blocks_only_its_mapped_gates(tmp_path: Path) -> None:
    gates = _compute(tmp_path, workflow_jobs=_workflow_jobs(failed_job="postgresql"))
    by_id = {item["gate_id"]: item for item in gates}

    assert by_id["postgresql-migrations"]["status"] == "BLOCK"
    assert by_id["tenant-isolation"]["status"] == "BLOCK"
    assert by_id["database-roles"]["status"] == "BLOCK"
    assert by_id["unit-quality"]["status"] == "PASS"


def test_missing_required_step_blocks_gate_despite_successful_job(tmp_path: Path) -> None:
    jobs = _workflow_jobs()
    verify = next(item for item in jobs["jobs"] if item["name"] == "verify")  # type: ignore[index]
    verify["steps"] = [  # type: ignore[index]
        step
        for step in verify["steps"]  # type: ignore[index]
        if step["name"] != "Dependency vulnerability audit"  # type: ignore[index]
    ]

    gates = _compute(tmp_path, workflow_jobs=jobs)
    by_id = {item["gate_id"]: item for item in gates}
    assert by_id["dependency-audit"]["status"] == "BLOCK"
    assert by_id["unit-quality"]["status"] == "PASS"


def test_tampered_artifact_blocks_integrity_gate(tmp_path: Path) -> None:
    root, checksums = _artifacts(tmp_path)
    (root / "package.whl").write_bytes(b"tampered")
    gates = compute_gate_input(
        workflow_run=_workflow_run(),
        workflow_jobs=_workflow_jobs(),
        artifact_root=root,
        checksum_path=checksums,
        expected_commit=COMMIT,
        expected_repository=REPOSITORY,
    )

    integrity = next(item for item in gates if item["gate_id"] == "artifact-integrity")
    assert integrity["status"] == "BLOCK"
    assert integrity["reason_codes"] == ["ARTIFACT_INTEGRITY_NOT_VERIFIED"]
