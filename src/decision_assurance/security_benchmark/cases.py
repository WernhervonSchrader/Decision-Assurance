from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

from .contracts import ROOT, digest, read_json
from .dataset import LOCK_PATH, _raw_rows, select_records, verify_file


@lru_cache(maxsize=1)
def _revision() -> str:
    return str(read_json(LOCK_PATH)["revision"])


def _base(family: str, variant: int) -> dict[str, Any]:
    layer = family[0]
    return {
        "test_id": f"DA-SEC-{family}-{variant:04}",
        "schema_version": "0.1",
        "source": "project-adversarial",
        "source_record_id": f"{family}-{variant}",
        "layer": layer,
        "family": family,
        "variant": variant,
        "attack_category": ["governance" if layer == "B" else "execution"],
        "classification_origin": "project-authored",
        "attack_surface": "decision_file" if layer == "B" else "execution_context",
        "scenario": family,
        "trust_boundary": "generator_to_governance" if layer == "B" else "approval_to_execution",
        "payload_reference": None,
        "expected_security_property": "no_unauthorized_execution",
        "expected_outcome": "BLOCK",
        "execution_mode": "simulation",
        "tenant_id": "tenant-a" if variant % 2 == 0 else "tenant-b",
        "locale": "en" if variant % 4 < 2 else "de",
        "unauthorized": True,
        "attack_ground_truth": None,
        "original_result": None,
        "original_attack_label": None,
        "provenance": {
            "dataset_revision": "project-v0.1",
            "license": "Apache-2.0",
            "content_sha256": digest({"family": family, "variant": variant}),
        },
    }


def own_cases(profile: str) -> list[dict[str, Any]]:
    families = [f"B{i}" for i in range(1, 7)] + [f"C{i}" for i in range(1, 8)]
    cases = [
        _base(family, variant)
        for family in families
        for variant in range(1 if profile == "smoke" else 8)
    ]
    for case in cases:
        if case["family"] == "B5":
            case["expected_outcome"] = "REVIEW" if case["variant"] < 4 else "BLOCK"
    for variant in range(1 if profile == "smoke" else 4):
        for family in ("B0", "C0"):
            case = _base(family, variant)
            case.update(
                expected_outcome="PASS", unauthorized=False, attack_category=["benign_control"]
            )
            cases.append(case)
    return cases


def source_case(row: dict[str, Any], path: str, *, benign: bool = False) -> dict[str, Any]:
    case = _base("B0", 0)
    case.update(
        {
            "test_id": "DA-SEC-A-" + row["content_sha256"][:24].upper(),
            "source": "microsoft-llmail-fp" if benign else "microsoft-llmail-inject",
            "source_record_id": row["source_record_id"],
            "layer": "A",
            "family": "A",
            "attack_category": ["benign_control"] if benign else json.loads(row["categories"]),
            "classification_origin": "source-benign-corpus"
            if benign
            else "project-derived-heuristic-v0.1",
            "attack_surface": "email_body",
            "scenario": row["scenario"],
            "trust_boundary": "untrusted_content_to_agent",
            "expected_outcome": "UNASSESSED",
            "unauthorized": None,
            "attack_ground_truth": False
            if benign
            else (
                bool(row["attack_ground_truth"])
                if row.get("attack_ground_truth") is not None
                else None
            ),
            "original_attack_label": json.loads(row["source_attack_label"])
            if row.get("source_attack_label")
            else None,
            "original_result": None if benign else json.loads(row["original_result"]),
            "payload_reference": {
                "path": path,
                "offset": row["offset"],
                "length": row["length"],
                "sha256": row["raw_sha256"],
            },
            "provenance": {
                "dataset_revision": _revision(),
                "license": "MIT",
                "content_sha256": row["content_sha256"],
            },
        }
    )
    return case


def selected_cases(index: Path, raw_root: Path, profile: str, seed: int) -> list[dict[str, Any]]:
    rows = select_records(index, 8 if profile == "smoke" else 1000, seed, require_attacks=True)
    cases = [
        source_case(row, Path(row["path"]).resolve().relative_to(raw_root.resolve()).as_posix())
        for row in rows
    ]
    return cases


def fp_cases(raw_root: Path) -> list[dict[str, Any]]:
    lock = read_json(LOCK_PATH)
    file = next(x for x in lock["files"] if x["kind"] == "false_positive")
    source = raw_root / file["path"]
    verify_file(source, file["sha256"], file["size"])
    emails = json.loads(source.read_text(encoding="utf8"))
    if (
        not isinstance(emails, list)
        or len(emails) != 203
        or not all(isinstance(x, str) for x in emails)
    ):
        raise ValueError("FP_SOURCE_INVALID")
    # Derived data-only wrappers preserve each original string exactly; original JSON stays intact.
    target = raw_root / "derived/fp.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    cases = []
    with target.open("wb") as stream:
        for i, email in enumerate(emails):
            record = {
                "RowKey": f"fp-{i:03}",
                "subject": "",
                "body": email,
                "scenario": "false_positive",
            }
            raw = (json.dumps(record, ensure_ascii=False) + "\n").encode()
            row = {
                "source_record_id": record["RowKey"],
                "scenario": "false_positive",
                "content_sha256": digest({"subject": "", "body": email}),
                "offset": stream.tell(),
                "length": len(raw),
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
            }
            stream.write(raw)
            case = source_case(row, "derived/fp.jsonl", benign=True)
            case["test_id"] += "-" + digest(record["RowKey"])[:8].upper()
            cases.append(case)
    return cases


def full_cases(raw_root: Path) -> Iterator[dict[str, Any]]:
    lock = read_json(LOCK_PATH)
    for file in lock["files"]:
        if file["kind"] != "raw":
            continue
        path = raw_root / file["path"]
        verify_file(path, file["sha256"], file["size"])
        for offset, length, record, sha in _raw_rows(path):
            from .dataset import classify

            original = record.get("objectives")
            if isinstance(original, str):
                try:
                    original = json.loads(original)
                except ValueError:
                    original = None
            row = {
                "source_record_id": record["RowKey"],
                "scenario": record["scenario"],
                "content_sha256": digest({"subject": record["subject"], "body": record["body"]}),
                "categories": json.dumps(classify(record["subject"], record["body"])),
                "original_result": json.dumps(original),
                "offset": offset,
                "length": length,
                "raw_sha256": sha,
            }
            case = source_case(row, file["path"])
            case["test_id"] += "-" + digest({"file": file["path"], "offset": offset})[:12].upper()
            yield case


def smoke_cases() -> list[dict[str, Any]]:
    fixture = ROOT / "benchmarks/security/fixtures/smoke-cases.json"
    return list(read_json(fixture)["cases"]) + own_cases("smoke")
