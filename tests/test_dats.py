import json
from pathlib import Path

import jsonschema
import pytest

from decision_assurance import evaluate


ROOT = Path(__file__).parent
SCHEMA = json.loads((ROOT / "scenario.schema.json").read_text(encoding="utf-8"))
CASES = sorted((ROOT / "scenarios").glob("*.json"))


@pytest.mark.parametrize("path", CASES, ids=lambda path: path.stem)
def test_scenario_contract(path: Path) -> None:
    case = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.validate(case, SCHEMA)


@pytest.mark.parametrize("path", CASES, ids=lambda path: path.stem)
def test_expected_outcome(path: Path) -> None:
    case = json.loads(path.read_text(encoding="utf-8"))
    assert evaluate(case) == case["expected"]


def test_exactly_ten_initial_scenarios() -> None:
    assert len(CASES) == 10

