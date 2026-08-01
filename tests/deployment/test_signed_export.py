from __future__ import annotations

import io
import json
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from decision_assurance.export.repository import InMemoryExportRepository
from decision_assurance.export.service import PilotExportService
from decision_assurance.export.signing import (
    FakeEd25519Signer,
    InMemoryVerificationKeyResolver,
    VerificationKey,
)
from decision_assurance.export.validator import ExportValidationError, main, validate_export
from decision_assurance.identity import ActorKind, Identity, Role
from decision_assurance.tenancy import TenantContext

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


def _snapshot() -> dict[str, object]:
    return {
        "decision/decision-file.json": {"decision_id": "quote-1", "status": "APPROVED"},
        "decision/assurance-report.json": {"outcome": "PASS", "findings": []},
        "intake/intake-records.json": [],
        "research/research-runs.json": [],
        "research/sources.json": [],
        "research/evidence.json": [],
        "audit/decision-events.json": [],
        "audit/intake-events.json": [],
        "audit/research-events.json": [],
        "audit/lifecycle-events.json": [],
    }


def _identity(tenant: str = "tenant-a") -> Identity:
    return Identity("auditor", TenantContext(tenant), Role.AUDITOR, ActorKind.HUMAN)


def _signed() -> tuple[bytes, InMemoryVerificationKeyResolver]:
    signer = FakeEd25519Signer(key_id="pilot-signing-2026-01", clock=lambda: NOW)
    resolver = InMemoryVerificationKeyResolver(
        {
            signer.key_id: VerificationKey(
                key_id=signer.key_id,
                public_key_pem=signer.public_key_pem,
                not_before=NOW - timedelta(days=1),
                not_after=NOW + timedelta(days=30),
            )
        }
    )
    content = (
        PilotExportService(
            InMemoryExportRepository({("tenant-a", "quote-1"): _snapshot()}),
            version="0.9.0",
            commit_sha="b" * 40,
            policy_versions={"sales-quote": "1"},
            signer=signer,
            event_schema_version="1.0.0",
            clock=lambda: NOW,
        )
        .build(_identity(), "quote-1")
        .content
    )
    return content, resolver


def _rewrite(content: bytes, name: str, transform: object) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(content))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        for member in source.namelist():
            payload = source.read(member)
            if member == name:
                value = json.loads(payload)
                payload = json.dumps(
                    transform(value), sort_keys=True, separators=(",", ":")
                ).encode()  # type: ignore[operator]
            target.writestr(member, payload)
    return output.getvalue()


def test_v09_export_is_signed_and_tenant_bound() -> None:
    content, resolver = _signed()
    report = validate_export(content, key_resolver=resolver, expected_tenant="tenant-a")

    assert report.valid
    assert report.provenance_status == "SIGNED_VALID"
    assert report.tenant_id == "tenant-a"
    assert report.key_id == "pilot-signing-2026-01"
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert "signature.json" in archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["schema_version"] == "0.9.0"
        assert manifest["event_schema_version"] == "1.0.0"
        assert manifest["tenant_id"] == "tenant-a"


def test_v09_signature_fails_for_manifest_tamper_wrong_tenant_and_key() -> None:
    content, resolver = _signed()
    tampered = _rewrite(content, "manifest.json", lambda value: {**value, "tenant_id": "tenant-b"})
    with pytest.raises(ExportValidationError, match="EXPORT_SIGNATURE_INVALID"):
        validate_export(tampered, key_resolver=resolver)
    with pytest.raises(ExportValidationError, match="EXPORT_TENANT_MISMATCH"):
        validate_export(content, key_resolver=resolver, expected_tenant="tenant-b")
    with pytest.raises(ExportValidationError, match="EXPORT_SIGNING_KEY_UNKNOWN"):
        validate_export(content, key_resolver=InMemoryVerificationKeyResolver({}))


@pytest.mark.parametrize("state", ["revoked", "expired", "not-yet-valid"])
def test_v09_rejects_unusable_key(state: str) -> None:
    content, original = _signed()
    key = original.resolve("pilot-signing-2026-01")
    assert key is not None
    if state == "revoked":
        replacement = VerificationKey(
            key.key_id,
            key.public_key_pem,
            key.not_before,
            key.not_after,
            revoked_at=NOW,  # gitleaks:allow -- synthetic public test-key lifecycle metadata
        )
    elif state == "expired":
        replacement = VerificationKey(
            key.key_id, key.public_key_pem, NOW - timedelta(days=2), NOW - timedelta(days=1)
        )
    else:
        replacement = VerificationKey(
            key.key_id, key.public_key_pem, NOW + timedelta(days=1), NOW + timedelta(days=2)
        )
    with pytest.raises(ExportValidationError, match="EXPORT_SIGNING_KEY_UNUSABLE"):
        validate_export(
            content,
            key_resolver=InMemoryVerificationKeyResolver({key.key_id: replacement}),
            verification_time=NOW,
        )


def test_algorithm_downgrade_and_missing_signature_fail_closed() -> None:
    content, resolver = _signed()
    downgraded = _rewrite(content, "signature.json", lambda value: {**value, "algorithm": "none"})
    with pytest.raises(ExportValidationError, match="EXPORT_SIGNATURE_ALGORITHM_UNSUPPORTED"):
        validate_export(downgraded, key_resolver=resolver)
    changed_time = _rewrite(
        content,
        "signature.json",
        lambda value: {**value, "signed_at": "2026-08-02T12:00:00Z"},
    )
    with pytest.raises(ExportValidationError, match="EXPORT_SIGNATURE_INVALID"):
        validate_export(changed_time, key_resolver=resolver, verification_time=NOW)

    source = zipfile.ZipFile(io.BytesIO(content))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        for name in source.namelist():
            if name != "signature.json":
                target.writestr(name, source.read(name))
    with pytest.raises(ExportValidationError, match="EXPORT_SIGNATURE_MISSING"):
        validate_export(output.getvalue(), key_resolver=resolver)


def test_legacy_export_is_explicitly_unsigned() -> None:
    archive = PilotExportService(
        InMemoryExportRepository({("tenant-a", "quote-1"): _snapshot()}),
        version="0.8.0",
        commit_sha="a" * 40,
        policy_versions={"sales-quote": "1"},
        clock=lambda: NOW,
    ).build(_identity(), "quote-1")

    report = validate_export(archive.content)
    assert report.valid
    assert report.provenance_status == "LEGACY_UNSIGNED"
    assert report.key_id is None


def test_offline_cli_verifies_signed_export_with_public_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    content, resolver = _signed()
    key = resolver.resolve("pilot-signing-2026-01")
    assert key is not None
    archive = tmp_path / "export.zip"
    registry = tmp_path / "keys.json"
    archive.write_bytes(content)
    registry.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "keys": [
                    {
                        "key_id": key.key_id,
                        "public_key_pem": key.public_key_pem.decode(),
                        "not_before": key.not_before.isoformat(),
                        "not_after": key.not_after.isoformat(),
                        "revoked_at": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "decision-assurance-validate-export",
            str(archive),
            "--key-registry",
            str(registry),
            "--expected-tenant",
            "tenant-a",
        ],
    )
    main()
    output = json.loads(capsys.readouterr().out)
    assert output["provenance_status"] == "SIGNED_VALID"
    assert output["key_id"] == "pilot-signing-2026-01"
