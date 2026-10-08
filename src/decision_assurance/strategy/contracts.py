from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ADAPTER_VERSION = "rif-3.4-rc3/da-1"
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]
Digest = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
Text = Annotated[str, Field(min_length=1, max_length=4096)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class TestCheck(Strict):
    id: Identifier
    required: bool
    status: Literal["PASS", "FAIL", "ERROR", "SKIP", "NOT_REPRODUCED", "EXPECTED_REJECTION"]
    expected_rejection: bool
    subject_ref: Text | None


class TestReport(Strict):
    id: Identifier
    method: Literal["cli", "function", "static", "manual"]
    subject: Text
    source_ref: Text | None
    source_commit: Text | None
    file_hashes: dict[Text, Digest]
    local_modifications: bool | None
    execution_status: Literal["COMPLETED", "ERROR", "NOT_EXECUTED", "INCOMPLETE"]
    exit_code: int | None
    checked_objects: Annotated[int, Field(ge=0, le=100000)]
    checks: Annotated[list[TestCheck], Field(max_length=1000)]


class Provenance(Strict):
    producer: Text
    locator: Text
    source_commit: Text | None
    local_modifications: bool | None
    file_hashes: dict[Text, Digest]
    test_reports: Annotated[list[TestReport], Field(max_length=100)]


class ImportEnvelope(Strict):
    adapter_version: Literal["rif-3.4-rc3/da-1"]
    tenant_id: Identifier
    decision_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
    expected_document_hash: Digest
    mode: Literal["draft", "baseline", "observation"]
    content_language: Annotated[str, Field(pattern=r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")]
    selected_option_id: Identifier | None
    provenance: Provenance
    artifact: dict[str, Any]


def test_report_reasons(
    reports: list[TestReport], known_subjects: set[str] | None = None
) -> list[str]:
    """Describe supplied execution evidence, never certify test correctness."""
    reasons: set[str] = set()
    for report in reports:
        if report.local_modifications is True:
            reasons.add("TEST_SOURCE_LOCAL_MODIFICATIONS")
        if not report.file_hashes or report.local_modifications is None:
            reasons.add("TEST_SOURCE_IDENTITY_INCOMPLETE")
        required = [check for check in report.checks if check.required]
        if report.checked_objects == 0 or not required:
            reasons.add("TEST_EMPTY")
        valid_refs = {**report.file_hashes}
        if known_subjects is not None:
            valid_refs.update(dict.fromkeys(known_subjects, ""))

        missing_references = not report.source_ref or any(
            not check.subject_ref
            or (known_subjects is not None and check.subject_ref not in valid_refs)
            for check in required
        )
        if missing_references:
            reasons.add("TEST_REFERENCES_MISSING")
        if report.execution_status != "COMPLETED" or report.exit_code not in (None, 0):
            reasons.add("TEST_INCOMPLETE")
        for check in required:
            if check.status in {"ERROR", "SKIP", "FAIL"}:
                reasons.add("TEST_INCOMPLETE")
            if check.status == "NOT_REPRODUCED":
                reasons.add("TEST_INCONCLUSIVE")
            if check.expected_rejection != (check.status == "EXPECTED_REJECTION"):
                reasons.add("TEST_EXPECTATION_MISMATCH")
        if report.method == "cli" and report.exit_code is None:
            reasons.add("TEST_INCOMPLETE")
        if report.method == "manual":
            reasons.add("TEST_MANUAL_INTERPRETATION")
        reasons.add(
            "TEST_REPORTED_COMPLETE_UNVERIFIED"
            if (
                report.checked_objects > 0
                and required
                and not missing_references
                and all(
                    c.status in {"PASS", "EXPECTED_REJECTION"}
                    and c.expected_rejection == (c.status == "EXPECTED_REJECTION")
                    for c in required
                )
                and report.execution_status == "COMPLETED"
                and (
                    report.exit_code == 0
                    if report.method == "cli"
                    else report.exit_code in (None, 0)
                )
            )
            else "TEST_EVIDENCE_UNVERIFIED"
        )
    return sorted(reasons)
