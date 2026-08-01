from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone

import pytest

from decision_assurance.export.repository import InMemoryExportRepository
from decision_assurance.export.service import ExportRejected, PilotExportService
from decision_assurance.export.validator import ExportValidationError, validate_export
from decision_assurance.identity import ActorKind, Identity, Role
from decision_assurance.tenancy import TenantContext

NOW = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)


def _snapshot() -> dict[str, object]:
    return {
        "decision/decision-file.json": {
            "decision_id": "quote-1",
            "status": "APPROVED",
            "outcome": "PASS",
            "created_by": {"id": "generator", "role": "GENERATOR", "kind": "HUMAN"},
            "approvals": [{"actor": {"id": "approver", "role": "APPROVER", "kind": "HUMAN"}}],
        },
        "decision/assurance-report.json": {"outcome": "PASS", "findings": []},
        "intake/intake-records.json": [{"intake_id": "quote-1", "status": "COMPILED"}],
        "research/research-runs.json": [{"research_run_id": "research-1", "status": "COMPLETED"}],
        "research/sources.json": [{"canonical_url": "https://public.example/policy"}],
        "research/evidence.json": [{"content_hash": "sha256:" + "a" * 64}],
        "audit/decision-events.json": [],
        "audit/intake-events.json": [],
        "audit/research-events.json": [],
        "audit/lifecycle-events.json": [],
    }


def _identity(tenant: str = "tenant-a") -> Identity:
    return Identity("auditor", TenantContext(tenant), Role.AUDITOR, ActorKind.HUMAN)


def test_export_is_portable_deterministic_and_validates_offline() -> None:
    repository = InMemoryExportRepository({("tenant-a", "quote-1"): _snapshot()})
    service = PilotExportService(
        repository,
        version="0.8.0",
        commit_sha="a" * 40,
        policy_versions={"sales-quote": "1", "export": "0.8.0"},
        clock=lambda: NOW,
    )

    first = service.build(_identity(), "quote-1")
    second = service.build(_identity(), "quote-1")
    report = validate_export(first.content)

    assert first.content == second.content
    assert report.valid
    assert report.case_ref == "quote-1"
    assert report.member_count == 10
    assert first.filename == "decision-assurance-pilot-export.zip"
    with zipfile.ZipFile(io.BytesIO(first.content)) as archive:
        assert archive.namelist()[0] == "manifest.json"
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["software"]["commit_sha"] == "a" * 40
        assert all("sha256" in item and "bytes" in item for item in manifest["members"])


def test_export_tamper_extra_member_and_traversal_are_rejected() -> None:
    repository = InMemoryExportRepository({("tenant-a", "quote-1"): _snapshot()})
    archive = PilotExportService(
        repository,
        version="0.8.0",
        commit_sha="a" * 40,
        policy_versions={"sales-quote": "1"},
        clock=lambda: NOW,
    ).build(_identity(), "quote-1")

    source = zipfile.ZipFile(io.BytesIO(archive.content))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        for name in source.namelist():
            payload = source.read(name)
            if name == "decision/decision-file.json":
                payload += b" "
            target.writestr(name, payload)
    with pytest.raises(ExportValidationError, match="EXPORT_CHECKSUM_MISMATCH"):
        validate_export(output.getvalue())

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        target.writestr("../secret.json", b"{}")
    with pytest.raises(ExportValidationError, match="EXPORT_PATH_REJECTED"):
        validate_export(output.getvalue())


def test_export_denies_cross_tenant_and_rejects_sensitive_fields() -> None:
    repository = InMemoryExportRepository({("tenant-a", "quote-1"): _snapshot()})
    service = PilotExportService(
        repository,
        version="0.8.0",
        commit_sha="a" * 40,
        policy_versions={"sales-quote": "1"},
        clock=lambda: NOW,
    )
    with pytest.raises(ExportRejected, match="CASE_NOT_FOUND"):
        service.build(_identity("tenant-b"), "quote-1")

    unsafe = _snapshot()
    unsafe["decision/decision-file.json"] = {"access_token": "canary-secret"}
    unsafe_service = PilotExportService(
        InMemoryExportRepository({("tenant-a", "quote-1"): unsafe}),
        version="0.8.0",
        commit_sha="a" * 40,
        policy_versions={"sales-quote": "1"},
        clock=lambda: NOW,
    )
    with pytest.raises(ExportRejected, match="SENSITIVE_EXPORT_FIELD"):
        unsafe_service.build(_identity(), "quote-1")
