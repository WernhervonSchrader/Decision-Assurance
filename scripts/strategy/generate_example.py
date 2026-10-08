"""Regenerate a synthetic offline preview fixture, not a productive import."""

import json
from pathlib import Path

from decision_assurance.audit import payload_hash
from decision_assurance.strategy.contracts import ADAPTER_VERSION

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    document = json.loads(
        (ROOT / "examples/decision-cases/low-risk-pass.json").read_text(encoding="utf-8")
    )
    document["decision_id"] = "DECISION-ORIGINAL"
    artifact = json.loads((ROOT / "examples/strategy/artifact.json").read_text(encoding="utf-8"))
    envelope = {
        "adapter_version": ADAPTER_VERSION,
        "tenant_id": "tenant-a",
        "decision_id": document["decision_id"],
        "expected_document_hash": payload_hash(document),
        "mode": "draft",
        "content_language": "en",
        "selected_option_id": "O-PILOT",
        "provenance": {
            "producer": "RIF synthetic handoff fixture",
            "locator": "local:examples/strategy/artifact.json",
            "source_commit": "e6e90e9dcd65db433a8fb7da92a8bb13dea75745",
            "local_modifications": True,
            "file_hashes": {},
            "test_reports": [],
        },
        "artifact": artifact,
    }
    for name, value in [("decision.json", document), ("envelope.json", envelope)]:
        (ROOT / "examples/strategy" / name).write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
