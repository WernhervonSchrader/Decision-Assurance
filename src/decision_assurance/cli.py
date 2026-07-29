from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from .benchmark import run_benchmark
from .decision_file import evaluate_decision_file, load_decision_file
from .engine import DecisionAssuranceEngine
from .identity import ActorKind, Identity, Role
from .intake.codec import policy_from_dict, to_dict, verification_from_dict
from .intake.compiler import DecisionFileCompiler
from .intake.confirmation import confirm_fact
from .intake.contracts import IntakeStatus
from .intake.extractor import DeterministicQuoteExtractor
from .intake.verification import InMemoryPolicyRegistry, IntakeVerifier
from .tenancy import TenantContext
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
    intake = commands.add_parser("intake")
    intake_commands = intake.add_subparsers(dest="intake_command", required=True)
    create_intake = intake_commands.add_parser("create")
    create_intake.add_argument("input", type=Path)
    create_intake.add_argument("--intake-id", required=True)
    create_intake.add_argument("--locale", choices=["de", "en"], default="en")
    create_intake.add_argument("--policy", type=Path)
    create_intake.add_argument("--output", type=Path, required=True)
    inspect_intake = intake_commands.add_parser("inspect")
    inspect_intake.add_argument("input", type=Path)
    confirm_intake = intake_commands.add_parser("confirm")
    confirm_intake.add_argument("input", type=Path)
    confirm_intake.add_argument("--fact-id", required=True)
    confirm_intake.add_argument("--action", choices=["CONFIRM", "CORRECT", "REJECT"], required=True)
    confirm_intake.add_argument("--new-value")
    confirm_intake.add_argument("--reason", required=True)
    confirm_intake.add_argument("--actor-id", required=True)
    confirm_intake.add_argument("--actor-role", choices=["VALIDATOR", "APPROVER"], required=True)
    confirm_intake.add_argument("--policy", type=Path)
    compile_intake = intake_commands.add_parser("compile")
    compile_intake.add_argument("input", type=Path)
    compile_intake.add_argument("--policy", type=Path, required=True)
    compile_intake.add_argument("--output", type=Path, required=True)
    evaluate_intake = intake_commands.add_parser("evaluate")
    evaluate_intake.add_argument("input", type=Path)
    args = parser.parse_args(argv)

    if args.command == "intake":
        return _run_intake(args)
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
        updated = TransitionPolicy().transition(
            document,
            args.target,
            {"id": args.actor_id, "role": args.actor_role, "kind": args.actor_kind},
        )
        args.input.write_text(
            json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {"status": updated["status"], "event": updated["audit_events"][-1]}, indent=2
            )
        )
    else:
        report = run_benchmark(args.manifest)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["failed"] == 0 else 1
    return 0


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _run_intake(args: argparse.Namespace) -> int:
    if args.intake_command == "create":
        policy = policy_from_dict(_read_json(args.policy)) if args.policy else None
        registry = InMemoryPolicyRegistry({"local": policy} if policy else {})
        extraction = DeterministicQuoteExtractor().extract(
            args.input.read_text(encoding="utf-8"), locale=args.locale, intake_id=args.intake_id
        )
        verification = IntakeVerifier(registry).verify("local", extraction)
        record: dict[str, object] = {
            "schema_version": "0.3.0",
            "intake_id": args.intake_id,
            "status": "READY" if verification.ready else "NEEDS_CONFIRMATION",
            "contract_ready": verification.ready,
            "extraction": to_dict(extraction),
            "verification": to_dict(verification),
            "confirmations": [],
        }
        _write_json(args.output, record)
        print(json.dumps(record, indent=2, ensure_ascii=False))
        return 0
    if args.intake_command == "inspect":
        print(json.dumps(_read_json(args.input), indent=2, ensure_ascii=False))
        return 0
    if args.intake_command == "confirm":
        record = _read_json(args.input)
        verification = verification_from_dict(record["verification"])  # type: ignore[arg-type]
        updated, confirmation = confirm_fact(
            verification,
            args.fact_id,
            action=args.action,
            new_value=args.new_value,
            reason=args.reason,
            occurred_at=datetime.now(timezone.utc).isoformat(),
            identity=Identity(
                args.actor_id,
                TenantContext("local"),
                Role(args.actor_role),
                ActorKind.HUMAN,
            ),
        )
        if args.policy:
            policy = policy_from_dict(_read_json(args.policy))
            updated = IntakeVerifier(InMemoryPolicyRegistry({"local": policy})).reverify(
                "local", updated
            )
        record["verification"] = to_dict(updated)
        record["contract_ready"] = updated.ready
        record["status"] = "READY" if updated.ready else "NEEDS_CONFIRMATION"
        confirmations = record.get("confirmations")
        if not isinstance(confirmations, list):
            confirmations = []
            record["confirmations"] = confirmations
        if not any(
            item.get("confirmation_id") == confirmation.confirmation_id for item in confirmations
        ):
            confirmations.append(to_dict(confirmation))
        _write_json(args.input, record)
        print(json.dumps(record, indent=2, ensure_ascii=False))
        return 0
    if args.intake_command == "compile":
        record = _read_json(args.input)
        decision = DecisionFileCompiler().compile(
            verification_from_dict(record["verification"]),  # type: ignore[arg-type]
            policy=policy_from_dict(_read_json(args.policy)),
            actor_id="system:intake-compiler",
            intake_status=IntakeStatus(str(record["status"])),
        )
        _write_json(args.output, decision)
        print(json.dumps(decision, indent=2, ensure_ascii=False))
        return 0
    payload = _read_json(args.input)
    _, result = evaluate_decision_file(payload)
    print(json.dumps(result.report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
