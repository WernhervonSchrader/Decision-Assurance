from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import ROOT, digest, read_json, safe_child
from .dataset import LOCK_PATH, read_payload, verify_file


def verify_smoke_origins(raw_root: Path) -> dict[str, Any]:
    """Reproduce bundled content/provenance checks against complete pinned originals."""
    fixture_root = ROOT / "benchmarks/security/fixtures"
    source_manifest = read_json(fixture_root / "source-manifest.json")
    lock = read_json(LOCK_PATH)
    if source_manifest["dataset_revision"] != lock["revision"]:
        raise ValueError("FIXTURE_REVISION_MISMATCH")
    files = {f["path"]: f for f in lock["files"]}
    cases = {c["test_id"]: c for c in read_json(fixture_root / "smoke-cases.json")["cases"]}
    verified: set[str] = set()
    for record in source_manifest["records"]:
        file = files[record["source_path"]]
        if file["sha256"] != record["source_file_sha256"]:
            raise ValueError("FIXTURE_SOURCE_HASH_MISMATCH")
        path = safe_child(raw_root, record["source_path"])
        if record["source_path"] not in verified:
            verify_file(path, file["sha256"], file["size"])
            verified.add(record["source_path"])
        case = cases[record["test_id"]]
        wrapper = read_payload(case["payload_reference"], fixture_root)
        if record["kind"] == "attack_submission":
            original = read_payload(
                {
                    "path": record["source_path"],
                    "offset": record["offset"],
                    "length": record["length"],
                    "sha256": record["source_record_sha256"],
                },
                raw_root,
            )
            if wrapper != {
                k: original[k] for k in ("RowKey", "subject", "body", "scenario", "objectives")
            }:
                raise ValueError("FIXTURE_ORIGINAL_CONTENT_CHANGED")
        else:
            originals = json.loads(path.read_text(encoding="utf8"))
            if wrapper["body"] != originals[record["source_array_index"]]:
                raise ValueError("FIXTURE_ORIGINAL_CONTENT_CHANGED")
        if (
            digest({"subject": wrapper["subject"], "body": wrapper["body"]})
            != record["content_sha256"]
        ):
            raise ValueError("FIXTURE_CONTENT_HASH_MISMATCH")
    if len(source_manifest["records"]) != len(cases):
        raise ValueError("FIXTURE_MANIFEST_CARDINALITY_MISMATCH")
    return {
        "verified_cases": len(cases),
        "dataset_revision": lock["revision"],
        "raw_files_verified": len(verified),
    }
