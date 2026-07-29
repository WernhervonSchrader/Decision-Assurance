import json
from pathlib import Path

from decision_assurance.case_store import CaseStore


def test_case_store_creates_canonical_structure(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    document = json.loads(
        (root / "examples" / "decision-cases" / "low-risk-pass.json").read_text(encoding="utf-8")
    )
    store = CaseStore(tmp_path)
    case = store.create(document)
    assert (case / "decision.json").is_file()
    for directory in CaseStore.SUBDIRECTORIES:
        assert (case / directory).is_dir()
    assert store.load(document["decision_id"])["decision_id"] == document["decision_id"]
