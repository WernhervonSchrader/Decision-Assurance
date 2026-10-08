import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from decision_assurance.strategy.contracts import ImportEnvelope

from .test_adapter import ROOT


def test_envelope_schema_and_delivered_example():
    from scripts.strategy.export_contract import PATHS

    expected = ImportEnvelope.model_json_schema()
    for path in PATHS:
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert {k: v for k, v in stored.items() if k not in {"$schema", "$id"}} == expected
    value = json.loads((ROOT / "examples/strategy/envelope.json").read_text(encoding="utf-8"))
    Draft202012Validator(stored, format_checker=FormatChecker()).validate(value)
    ImportEnvelope.model_validate(value)


def test_snapshot_hashes_identify_copied_rif_documents():
    import hashlib

    manifest = json.loads((ROOT / "schemas/strategy/RIF-SNAPSHOT.json").read_text(encoding="utf-8"))
    assert manifest["commit_identifies_copied_files"] is False
    assert manifest["source_worktree_has_local_changes"] is True
    for name, digest in manifest["files"].items():
        path = (
            ROOT
            / (
                "src/decision_assurance/schemas/strategy/rif"
                if name.startswith("schemas/")
                else "tests/strategy/fixtures"
            )
            / Path(name).name
        )
        assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == digest
