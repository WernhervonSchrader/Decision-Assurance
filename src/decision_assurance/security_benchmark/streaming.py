from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from contextlib import closing
from itertools import islice
from pathlib import Path
from typing import Any

from .contracts import digest
from .runner import run_cases


def run_streaming(
    cases: Iterable[dict[str, Any]],
    output: Path,
    *,
    payload_root: Path,
    profile: str = "full",
    seed: int = 42,
    batch_size: int = 1000,
) -> dict[str, Any]:
    """Bounded-memory full run with verified per-batch checkpoints and complete JSONL results."""
    if not 1 <= batch_size <= 10000:
        raise ValueError("BATCH_SIZE_INVALID")
    output.mkdir(parents=True, exist_ok=True)
    iterator = iter(cases)
    summary = run_cases([], output / "work", profile=profile, seed=seed)
    summary["results_scope"] = (
        "B/C and security-failure sample; complete A/B/C results in results.jsonl"
    )
    case_hash = hashlib.sha256(b"[")
    stream_hash = hashlib.sha256()
    stream_size = 0
    batch_number = 0
    with (
        closing(sqlite3.connect(output / "seen-cases.sqlite")) as db,
        (output / "results.jsonl.part").open("wb") as sink,
    ):
        db.execute("CREATE TABLE IF NOT EXISTS seen(id TEXT PRIMARY KEY)")
        db.execute("DELETE FROM seen")
        while batch := list(islice(iterator, batch_size)):
            for case in batch:
                try:
                    db.execute("INSERT INTO seen VALUES(?)", (case["test_id"],))
                except sqlite3.IntegrityError:
                    raise ValueError("DUPLICATE_TEST_ID") from None
            checkpoint = output / "checkpoints" / f"batch-{batch_number:06}.jsonl"
            report = run_cases(
                batch,
                output / "work",
                payload_root=payload_root,
                checkpoint=checkpoint,
                profile=profile,
                seed=seed,
            )
            for row in report["results"]:
                if summary["total_cases"]:
                    case_hash.update(b",")
                case_hash.update(json.dumps(row["case_sha256"]).encode())
                summary["total_cases"] += 1
                raw = (json.dumps(row, sort_keys=True) + "\n").encode()
                sink.write(raw)
                stream_hash.update(raw)
                stream_size += len(raw)
                if row["layer"] != "A" or row["status"] == "SECURITY_FAILURE":
                    if len(summary["results"]) < 1000:
                        summary["results"].append(row)
            summary["evaluated"] += report["evaluated"]
            for key in (
                "checkpoint_reused_cases",
                "fresh_case_measurements",
                "fresh_security_components",
            ):
                summary[key] += report[key]
            for status, count in report["counts"].items():
                summary["counts"][status] += count
            for name, metric in report["metrics"].items():
                aggregate = summary["metrics"][name]
                for field in ("numerator", "denominator", "excluded"):
                    aggregate[field] += metric[field]
            for key in ("evaluable", "successful_tool_objectives", "tool_proposals"):
                summary["original_observations"][key] += report["original_observations"][key]
            for key, count in report["measurement_counts"].items():
                summary["measurement_counts"][key] += count
            summary["critical_findings"] += report["critical_findings"][
                : max(0, 1000 - len(summary["critical_findings"]))
            ]
            batch_number += 1
            db.commit()
        if len(list((output / "checkpoints").glob("batch-*.jsonl"))) > batch_number:
            raise ValueError("CHECKPOINT_CASE_SET_SHORTENED")
    case_hash.update(b"]")
    summary["case_set_sha256"] = case_hash.hexdigest()
    for metric in summary["metrics"].values():
        metric["value"] = (
            metric["numerator"] / metric["denominator"] if metric["denominator"] else None
        )
    summary["result_stream"] = {
        "path": "results.jsonl",
        "sha256": stream_hash.hexdigest(),
        "size": stream_size,
        "cases": summary["total_cases"],
    }
    (output / "results.jsonl.part").replace(output / "results.jsonl")
    summary["stream_summary_sha256"] = digest(
        {"cases": summary["case_set_sha256"], "results": summary["result_stream"]}
    )
    return summary
