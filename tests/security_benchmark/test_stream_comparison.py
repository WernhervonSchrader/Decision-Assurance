import copy
import hashlib
import json
from pathlib import Path

import pytest

from decision_assurance.security_benchmark.cases import own_cases
from decision_assurance.security_benchmark.runner import compare_stream_reports
from decision_assurance.security_benchmark.streaming import run_streaming


def test_complete_stream_comparison_and_mutation_outside_summary(tmp_path: Path) -> None:
    cases = own_cases("smoke")
    first = run_streaming(cases, tmp_path / "first", payload_root=tmp_path, batch_size=4)
    second = run_streaming(cases, tmp_path / "second", payload_root=tmp_path, batch_size=4)
    assert compare_stream_reports(first, second, tmp_path / "first", tmp_path / "second")[
        "regression_pass"
    ]
    path = tmp_path / "second/results.jsonl"
    lines = path.read_text().splitlines()
    row = json.loads(lines[0])
    row["audit_complete"] = False
    lines[0] = json.dumps(row)
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="CHECKSUM"):
        compare_stream_reports(first, second, tmp_path / "first", tmp_path / "second")
    changed = copy.deepcopy(second)
    raw = path.read_bytes()
    changed["result_stream"].update(sha256=hashlib.sha256(raw).hexdigest(), size=len(raw))
    assert not compare_stream_reports(first, changed, tmp_path / "first", tmp_path / "second")[
        "regression_pass"
    ]
