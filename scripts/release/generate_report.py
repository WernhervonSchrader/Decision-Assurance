from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

from decision_assurance.production import GateResult, ReleaseStatus
from decision_assurance.release_verification import ReleaseVerifier, report_to_dict


def generate_report(input_path: Path, output_path: Path, version: str, commit_sha: str) -> None:
    raw: Any = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("INVALID_GATE_EVIDENCE")
    gates = tuple(
        GateResult(
            gate_id=item["gate_id"],
            status=ReleaseStatus(item["status"]),
            reason_codes=tuple(item.get("reason_codes", ())),
            evidence_refs=tuple(item["evidence_refs"]),
        )
        for item in raw
    )
    report = ReleaseVerifier().verify(
        version=version,
        commit_sha=commit_sha,
        generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        gates=gates,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report_to_dict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    schema_path = Path("schemas/production/release-verification.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(
        report_to_dict(report)
    )
    if report.status is not ReleaseStatus.PASS:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default="0.5.0")
    parser.add_argument("--commit-sha", required=True)
    args = parser.parse_args()
    generate_report(args.input, args.output, args.version, args.commit_sha)


if __name__ == "__main__":
    main()
