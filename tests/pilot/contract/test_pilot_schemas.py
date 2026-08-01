from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).parents[3]


def _validator(name: str) -> Draft202012Validator:
    public = ROOT / "schemas" / "production" / f"{name}.schema.json"
    packaged = (
        ROOT / "src" / "decision_assurance" / "schemas" / "production" / f"{name}.schema.json"
    )
    assert public.read_bytes() == packaged.read_bytes()
    return Draft202012Validator(
        json.loads(public.read_text(encoding="utf-8")), format_checker=FormatChecker()
    )


def test_export_manifest_contract_is_strict_and_versioned() -> None:
    value = {
        "schema_version": "0.8.0",
        "export_id": "export-1",
        "case_ref": "quote-1",
        "generated_at": "2026-08-01T08:00:00Z",
        "software": {"version": "0.8.0", "commit_sha": "a" * 40},
        "policy_versions": {"sales_quote": "1"},
        "members": [{"path": "decision/decision-file.json", "sha256": "b" * 64, "bytes": 42}],
    }
    validator = _validator("pilot-export")

    validator.validate(value)
    with pytest.raises(ValidationError):
        validator.validate({**value, "access_token": "forbidden"})
    with pytest.raises(ValidationError):
        validator.validate(
            {**value, "members": [{"path": "../secret.json", "sha256": "b" * 64, "bytes": 42}]}
        )


def test_data_lifecycle_contract_rejects_soft_delete_and_unknown_data() -> None:
    value = {
        "schema_version": "0.8.0",
        "request_id": "delete-1",
        "case_ref_hash": "sha256:" + "a" * 64,
        "status": "COMPLETED",
        "requested_at": "2026-08-01T08:00:00Z",
        "completed_at": "2026-08-01T08:00:01Z",
        "reason_code": "RETENTION_EXPIRED",
        "legal_hold_active": False,
        "event_hash": "sha256:" + "b" * 64,
        "previous_event_hash": None,
    }
    validator = _validator("data-lifecycle")

    validator.validate(value)
    with pytest.raises(ValidationError):
        validator.validate({**value, "status": "HIDDEN"})
    with pytest.raises(ValidationError):
        validator.validate({**value, "decision_text": "must not be retained"})
