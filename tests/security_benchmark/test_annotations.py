import json
from pathlib import Path

import pytest

from decision_assurance.security_benchmark.annotations import annotate_index, object_items
from decision_assurance.security_benchmark.dataset import build_index, select_records


def test_annotation_streaming_and_grounded_attack_selection(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    labels = tmp_path / "labels.json"
    raw.write_text(
        json.dumps(
            {
                "RowKey": "one",
                "subject": "Subject",
                "body": "Body",
                "scenario": "level1a",
                "objectives": "{}",
            }
        )
        + "\n",
        encoding="utf8",
    )
    key = "Subject of the email: Subject.   Body: Body"
    source = {
        key: {"attack_attempt": "True", "reason": "judge", "judge_category": "direct instructions"}
    }
    labels.write_text(json.dumps(source), encoding="utf8")
    assert list(object_items(labels)) == list(source.items())
    index = tmp_path / "index.sqlite"
    build_index([raw], index)
    result = annotate_index(index, [labels])
    assert result["annotation_counts"] == {"1": 1}
    assert select_records(index, 1, 42, require_attacks=True)[0]["attack_ground_truth"] == 1
    assert annotate_index(index, [labels]) == result
    second = tmp_path / "labels2.json"
    second.write_text(json.dumps({key: {"attack_attempt": "False", "reason": "judge"}}))
    assert annotate_index(index, [labels, second])["annotation_counts"] == {"unknown": 1}
    with pytest.raises(ValueError, match="INSUFFICIENT"):
        select_records(index, 1, 42, require_attacks=True)


@pytest.mark.parametrize("content", ["[]", '{"x":', '{"x": 2}', '{"x":{}},', '{"x":{},}'])
def test_annotation_parser_rejects_invalid_or_unbounded_records(
    tmp_path: Path, content: str
) -> None:
    path = tmp_path / "bad.json"
    path.write_text(content)
    with pytest.raises(ValueError, match="ANNOTATION"):
        list(object_items(path))
