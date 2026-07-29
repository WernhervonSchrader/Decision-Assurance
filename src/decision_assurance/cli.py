from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .benchmark import run_benchmark
from .decision_file import evaluate_decision_file, load_decision_file
from .engine import DecisionAssuranceEngine
from .transitions import TransitionPolicy


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Decision Assurance reference engine")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "evaluate", "report"):
        command = commands.add_parser(name)
        command.add_argument("input", type=Path)
    transition = commands.add_parser("transition")
    transition.add_argument("input", type=Path)
    transition.add_argument("target")
    transition.add_argument("--actor-id", required=True)
    transition.add_argument("--actor-role", required=True, choices=["VALIDATOR", "APPROVER"])
    transition.add_argument("--actor-kind", default="HUMAN", choices=["HUMAN", "AGENT", "SERVICE"])
    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)

    if args.command == "validate":
        load_decision_file(args.input)
        print(json.dumps({"valid": True, "path": str(args.input)}))
    elif args.command in {"evaluate", "report"}:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        if "schema_version" in payload:
            _, result = evaluate_decision_file(payload)
        else:
            result = DecisionAssuranceEngine().assess(payload)
        print(json.dumps(result.report, indent=2, ensure_ascii=False))
    elif args.command == "transition":
        document = load_decision_file(args.input)
        updated = TransitionPolicy().transition(document, args.target, {"id":args.actor_id,"role":args.actor_role,"kind":args.actor_kind})
        args.input.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"status": updated["status"], "event": updated["audit_events"][-1]}, indent=2))
    else:
        report = run_benchmark(args.manifest)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["failed"] == 0 else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
