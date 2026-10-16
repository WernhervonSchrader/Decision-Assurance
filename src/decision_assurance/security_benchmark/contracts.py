from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[3]
SCHEMA = Path(__file__).parents[1] / "schemas/security-benchmark/security-case.schema.json"
MAX_RECORD_BYTES = 1_048_576


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 16 * MAX_RECORD_BYTES:
        raise ValueError("JSON_TOO_LARGE")
    data = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(data, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return cast(dict[str, Any], data)


@lru_cache(maxsize=1)
def _case_validator() -> Draft202012Validator:
    return Draft202012Validator(read_json(SCHEMA))


def validate_case(case: dict[str, Any]) -> None:
    if list(_case_validator().iter_errors(case)):
        raise ValueError("CASE_INVALID")
    if case["layer"] == "A" and case["expected_outcome"] != "UNASSESSED":
        raise ValueError("CASE_INVALID_SOURCE_LABEL_POLICY_MAPPING")
    if case["layer"] != "A" and case["payload_reference"] is not None:
        raise ValueError("CASE_INVALID_PAYLOAD_BOUNDARY")


def safe_child(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative or ":" in relative:
        raise ValueError("PATH_OUTSIDE_DATASET")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("PATH_OUTSIDE_DATASET")
    return resolved
