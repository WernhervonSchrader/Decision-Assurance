import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from decision_assurance.benchmark import run_benchmark

ROOT = Path(__file__).parents[1]
DATS = ROOT / "benchmarks" / "dats"
CATALOG = DATS / "v0.1.0" / "catalog.json"


def test_catalog_and_all_cases_match_public_contracts() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    catalog_schema = json.loads(
        (DATS / "schemas" / "dats-catalog.schema.json").read_text(encoding="utf-8")
    )
    case_schema = json.loads(
        (DATS / "schemas" / "dats-case.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(catalog_schema).validate(catalog)
    assert catalog["case_count"] == len(catalog["cases"]) == 10
    for item in catalog["cases"]:
        case = json.loads((CATALOG.parent / item["path"]).read_text(encoding="utf-8"))
        Draft202012Validator(case_schema).validate(case)
        assert case["id"] == item["id"]


def test_owasp_source_record_is_valid_and_does_not_overclaim() -> None:
    source_schema = json.loads(
        (DATS / "schemas" / "external-source.schema.json").read_text(encoding="utf-8")
    )
    source = json.loads(
        (DATS / "sources" / "owasp-state-agentic-ai-security-governance-2.01.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(
        source_schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    ).validate(source)
    assert source["publisher"] == "OWASP GenAI Security Project"
    assert source["local_copy_included"] is False
    assert source["mapping_status"] == "PROJECT_INTERPRETATION_NOT_OWASP_ENDORSEMENT"


def test_legacy_scenarios_remain_identical_to_canonical_tasks_and_results() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    for item in catalog["cases"]:
        case = json.loads((CATALOG.parent / item["path"]).read_text(encoding="utf-8"))
        legacy = json.loads(
            (ROOT / "tests" / "scenarios" / f"{item['id'].lower()}.json").read_text(
                encoding="utf-8"
            )
        )
        assert legacy["input"] == case["task"]["input"]
        assert legacy["expected"] == {
            "outcome": case["expected_result"]["engine_outcome"],
            "reason_codes": case["expected_result"]["reason_codes"],
            "human_review": case["expected_result"]["human_review"],
        }


def test_changed_normative_result_is_reported_as_regression(tmp_path: Path) -> None:
    copied = tmp_path / "dats"
    shutil.copytree(DATS, copied)
    case_path = copied / "v0.1.0" / "cases" / "DATS-001.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["expected_result"]["gate_decision"] = "FAIL"
    case_path.write_text(json.dumps(case), encoding="utf-8")
    report = run_benchmark(copied / "v0.1.0" / "catalog.json")
    assert report["passed"] == 9
    assert report["failed"] == 1
    assert report["results"][0]["id"] == "DATS-001"


def test_catalog_cannot_escape_dataset_root(tmp_path: Path) -> None:
    copied = tmp_path / "dats"
    shutil.copytree(DATS, copied)
    catalog_path = copied / "v0.1.0" / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["cases"][0]["path"] = "../outside.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    with pytest.raises(ValueError, match="DATS_SCHEMA_INVALID|DATS_CASE_PATH_OUTSIDE_DATASET"):
        run_benchmark(catalog_path)
