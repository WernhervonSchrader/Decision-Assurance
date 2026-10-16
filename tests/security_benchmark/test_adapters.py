import copy
import hashlib
import json
from pathlib import Path

import pytest

from decision_assurance.security_benchmark.adapters import run_governance, run_source
from decision_assurance.security_benchmark.cases import own_cases, source_case
from decision_assurance.security_benchmark.contracts import digest, safe_child


def test_fake_human_approval_is_an_observed_lifecycle_bypass(tmp_path: Path) -> None:
    case = next(c for c in own_cases("smoke") if c["family"] == "B3")
    result = run_governance(case, tmp_path)
    assert result["component_executed"]
    assert result["lifecycle_state"] == "APPROVED"
    assert result["status"] == "SECURITY_FAILURE"
    assert result["governance_escape"] is True
    assert result["executed"] is None
    assert result["audit_complete"] is False


def test_original_objectives_never_become_fresh_model_measurements(tmp_path: Path) -> None:
    objectives = dict.fromkeys(
        [
            "email.retrieved",
            "defense.undetected",
            "exfil.sent",
            "exfil.destination",
            "exfil.content",
        ],
        True,
    )
    record = {
        "RowKey": "id-1",
        "subject": "Test fixture",
        "body": "Untrusted content",
        "scenario": "level1a",
        "objectives": json.dumps(objectives),
    }
    raw = (json.dumps(record) + "\n").encode()
    (tmp_path / "source.jsonl").write_bytes(raw)
    row = {
        "source_record_id": "id-1",
        "scenario": "level1a",
        "content_sha256": digest({"subject": record["subject"], "body": record["body"]}),
        "categories": json.dumps(["unclassified"]),
        "original_result": json.dumps(objectives),
        "offset": 0,
        "length": len(raw),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
    }
    case = source_case(row, "source.jsonl")
    result = run_source(case, tmp_path)
    assert result["original_attack_success"] is True
    assert result["original_tool_proposed"] is True
    assert result["attack_success"] is result["tool_proposed"] is result["executed"] is None
    assert result["status"] == "INCONCLUSIVE"
    modified = copy.deepcopy(case)
    modified["original_result"]["exfil.sent"] = False
    with pytest.raises(ValueError, match="OBJECTIVES"):
        run_source(modified, tmp_path)


@pytest.mark.parametrize(
    "path",
    ["../secret", "/absolute", "C:/outside", "folder\\..\\secret", "https://example.invalid"],
)
def test_payload_paths_cannot_escape_root(tmp_path: Path, path: str) -> None:
    with pytest.raises(ValueError, match="PATH"):
        safe_child(tmp_path, path)


def test_missing_adapter_or_broken_fixture_is_never_a_pass(tmp_path: Path) -> None:
    from decision_assurance.security_benchmark.runner import run_cases

    case = copy.deepcopy(own_cases("smoke")[0])
    case.update(layer="A", family="A", expected_outcome="UNASSESSED")
    case["payload_reference"] = {
        "path": "missing.jsonl",
        "offset": 0,
        "length": 1,
        "sha256": "0" * 64,
    }
    result = run_cases([case], tmp_path, payload_root=tmp_path)["results"][0]
    assert result["status"] == "INFRASTRUCTURE_ERROR"
    assert not result["component_executed"]
