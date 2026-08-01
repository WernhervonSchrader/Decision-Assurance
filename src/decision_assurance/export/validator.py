from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

from .service import EXPORT_MEMBERS
from .signing import (
    InMemoryVerificationKeyResolver,
    SignatureEnvelope,
    VerificationKey,
    VerificationKeyResolver,
    verify_ed25519,
)

MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 40 * 1024 * 1024


class ExportValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ValidationReport:
    valid: bool
    case_ref: str
    member_count: int
    export_id: str
    provenance_status: str = "LEGACY_UNSIGNED"
    tenant_id: str | None = None
    key_id: str | None = None


def validate_export(
    content: bytes,
    *,
    key_resolver: VerificationKeyResolver | None = None,
    expected_tenant: str | None = None,
    verification_time: datetime | None = None,
) -> ValidationReport:
    if not content or len(content) > MAX_ARCHIVE_BYTES:
        raise ExportValidationError("EXPORT_SIZE_REJECTED")
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise ExportValidationError("INVALID_EXPORT_ARCHIVE") from None
    with archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)):
            raise ExportValidationError("DUPLICATE_EXPORT_MEMBER")
        if any(not _safe_path(name) for name in names):
            raise ExportValidationError("EXPORT_PATH_REJECTED")
        try:
            manifest_bytes = archive.read("manifest.json")
            manifest = cast(dict[str, Any], json.loads(manifest_bytes))
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError):
            raise ExportValidationError("INVALID_EXPORT_MANIFEST") from None
        version = manifest.get("schema_version")
        if version not in {"0.8.0", "0.9.0"}:
            raise ExportValidationError("EXPORT_VERSION_UNSUPPORTED")
        expected = {"manifest.json", *EXPORT_MEMBERS}
        if version == "0.9.0":
            expected.add("signature.json")
        if set(names) != expected:
            if version == "0.9.0" and "signature.json" not in names:
                raise ExportValidationError("EXPORT_SIGNATURE_MISSING")
            raise ExportValidationError("EXPORT_MEMBER_SET_MISMATCH")
        if sum(item.file_size for item in infos) > MAX_UNCOMPRESSED_BYTES:
            raise ExportValidationError("EXPORT_SIZE_REJECTED")
        _validate_manifest(manifest, str(version))
        declared = manifest["members"]
        if not isinstance(declared, list):
            raise ExportValidationError("INVALID_EXPORT_MANIFEST")
        by_path = {item["path"]: item for item in declared}
        if set(by_path) != set(EXPORT_MEMBERS) or len(by_path) != len(declared):
            raise ExportValidationError("EXPORT_MEMBER_SET_MISMATCH")
        parsed_members: dict[str, object] = {}
        for name in EXPORT_MEMBERS:
            payload = archive.read(name)
            declaration = by_path[name]
            if declaration["bytes"] != len(payload) or not _constant_equal(
                declaration["sha256"], hashlib.sha256(payload).hexdigest()
            ):
                raise ExportValidationError("EXPORT_CHECKSUM_MISMATCH")
            try:
                parsed_members[name] = json.loads(payload)
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise ExportValidationError("INVALID_EXPORT_MEMBER") from None
        _validate_audit_chains(parsed_members)
        provenance_status = "LEGACY_UNSIGNED"
        tenant_id: str | None = None
        key_id: str | None = None
        if version == "0.9.0":
            tenant_id = str(manifest["tenant_id"])
            if expected_tenant is not None and not _constant_equal(tenant_id, expected_tenant):
                raise ExportValidationError("EXPORT_TENANT_MISMATCH")
            key_id = _validate_signature(
                archive.read("signature.json"),
                manifest_bytes,
                key_resolver,
                verification_time or datetime.now(timezone.utc),
            )
            provenance_status = "SIGNED_VALID"
        return ValidationReport(
            valid=True,
            case_ref=str(manifest["case_ref"]),
            member_count=len(declared),
            export_id=str(manifest["export_id"]),
            provenance_status=provenance_status,
            tenant_id=tenant_id,
            key_id=key_id,
        )


def _validate_manifest(manifest: dict[str, Any], version: str) -> None:
    filename = "pilot-export-v0.9.schema.json" if version == "0.9.0" else "pilot-export.schema.json"
    resource = files("decision_assurance.schemas").joinpath(f"production/{filename}")
    schema = json.loads(resource.read_text(encoding="utf-8"))
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(manifest)
    )
    if errors:
        raise ExportValidationError("INVALID_EXPORT_MANIFEST")


def _validate_signature(
    raw: bytes,
    manifest_bytes: bytes,
    resolver: VerificationKeyResolver | None,
    verification_time: datetime,
) -> str:
    try:
        envelope = cast(dict[str, object], json.loads(raw))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ExportValidationError("EXPORT_SIGNATURE_INVALID") from None
    if set(envelope) != {"format_version", "algorithm", "key_id", "signed_at", "signature"}:
        raise ExportValidationError("EXPORT_SIGNATURE_INVALID")
    if envelope.get("format_version") != "1.0.0":
        raise ExportValidationError("EXPORT_SIGNATURE_VERSION_UNSUPPORTED")
    if envelope.get("algorithm") != "EdDSA":
        raise ExportValidationError("EXPORT_SIGNATURE_ALGORITHM_UNSUPPORTED")
    key_id = envelope.get("key_id")
    signature = envelope.get("signature")
    if not isinstance(key_id, str) or not isinstance(signature, str) or resolver is None:
        raise ExportValidationError("EXPORT_SIGNING_KEY_UNKNOWN")
    key = resolver.resolve(key_id)
    if key is None:
        raise ExportValidationError("EXPORT_SIGNING_KEY_UNKNOWN")
    try:
        signed_at = datetime.fromisoformat(str(envelope["signed_at"]).replace("Z", "+00:00"))
    except ValueError:
        raise ExportValidationError("EXPORT_SIGNATURE_INVALID") from None
    if (
        signed_at.tzinfo is None
        or not key.usable_at(signed_at)
        or not key.usable_at(verification_time)
    ):
        raise ExportValidationError("EXPORT_SIGNING_KEY_UNUSABLE")
    signature_envelope = SignatureEnvelope(
        str(envelope["format_version"]),
        str(envelope["algorithm"]),
        key_id,
        str(envelope["signed_at"]),
        signature,
    )
    if not verify_ed25519(key.public_key_pem, manifest_bytes, signature, signature_envelope):
        raise ExportValidationError("EXPORT_SIGNATURE_INVALID")
    return key_id


def _safe_path(name: str) -> bool:
    if "\\" in name or name.startswith("/") or ":" in name:
        return False
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts


def _constant_equal(left: object, right: str) -> bool:
    import hmac

    return isinstance(left, str) and hmac.compare_digest(left, right)


def _validate_audit_chains(members: dict[str, object]) -> None:
    for name in (
        "audit/decision-events.json",
        "audit/intake-events.json",
        "audit/research-events.json",
    ):
        events = members[name]
        if not isinstance(events, list) or any(not isinstance(item, dict) for item in events):
            raise ExportValidationError("INVALID_EXPORT_AUDIT_CHAIN")
        core_previous_by_stream: dict[str, str] = {}
        for event in cast(list[dict[str, object]], events):
            stream = _audit_stream(name, event)
            previous = event.get("previous_event_hash")
            if stream not in core_previous_by_stream:
                if previous is not None:
                    raise ExportValidationError("INVALID_EXPORT_AUDIT_CHAIN")
            elif previous != core_previous_by_stream[stream]:
                raise ExportValidationError("INVALID_EXPORT_AUDIT_CHAIN")
            core_previous_by_stream[stream] = _prefixed_hash(event)

    lifecycle = members["audit/lifecycle-events.json"]
    if not isinstance(lifecycle, list) or any(not isinstance(item, dict) for item in lifecycle):
        raise ExportValidationError("INVALID_EXPORT_AUDIT_CHAIN")
    previous_by_stream: dict[str, str] = {}
    for event in cast(list[dict[str, object]], lifecycle):
        request_id = event.get("request_id")
        event_hash = event.get("event_hash")
        if not isinstance(request_id, str) or not isinstance(event_hash, str):
            raise ExportValidationError("INVALID_EXPORT_AUDIT_CHAIN")
        expected_previous = previous_by_stream.get(request_id)
        if event.get("previous_event_hash") != expected_previous:
            raise ExportValidationError("INVALID_EXPORT_AUDIT_CHAIN")
        hash_payload = {
            key: value
            for key, value in event.items()
            if key not in {"schema_version", "event_hash"}
        }
        if not _constant_equal(event_hash, _prefixed_hash(hash_payload)):
            raise ExportValidationError("INVALID_EXPORT_AUDIT_CHAIN")
        previous_by_stream[request_id] = event_hash


def _prefixed_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _audit_stream(name: str, event: dict[str, object]) -> str:
    if name == "audit/decision-events.json":
        return "decision"
    event_id = event.get("event_id")
    if not isinstance(event_id, str):
        raise ExportValidationError("INVALID_EXPORT_AUDIT_CHAIN")
    markers = (
        ("audit/intake-events.json", (":intake-audit:",)),
        ("audit/research-events.json", (":research-audit:", ":egress:")),
    )
    for member, candidates in markers:
        if name == member:
            for marker in candidates:
                if marker in event_id:
                    stream = event_id.rsplit(marker, 1)[0]
                    if stream:
                        return stream
    raise ExportValidationError("INVALID_EXPORT_AUDIT_CHAIN")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline Decision Assurance pilot export validator"
    )
    parser.add_argument("archive", type=Path)
    parser.add_argument("--key-registry", type=Path)
    parser.add_argument("--expected-tenant")
    arguments = parser.parse_args()
    if arguments.archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise SystemExit("EXPORT_SIZE_REJECTED")
    try:
        resolver = _load_key_registry(arguments.key_registry) if arguments.key_registry else None
        report = validate_export(
            arguments.archive.read_bytes(),
            key_resolver=resolver,
            expected_tenant=arguments.expected_tenant,
        )
    except (OSError, ExportValidationError) as error:
        raise SystemExit(str(error)) from None
    print(
        json.dumps(
            {
                "valid": report.valid,
                "case_ref": report.case_ref,
                "export_id": report.export_id,
                "member_count": report.member_count,
                "provenance_status": report.provenance_status,
                "tenant_id": report.tenant_id,
                "key_id": report.key_id,
            },
            sort_keys=True,
        )
    )


def _load_key_registry(path: Path) -> InMemoryVerificationKeyResolver:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        raise ExportValidationError("INVALID_VERIFICATION_KEY_REGISTRY") from None
    if (
        not isinstance(raw, dict)
        or set(raw) != {"schema_version", "keys"}
        or raw["schema_version"] != "1.0.0"
        or not isinstance(raw["keys"], list)
    ):
        raise ExportValidationError("INVALID_VERIFICATION_KEY_REGISTRY")
    keys: dict[str, VerificationKey] = {}
    for item in raw["keys"]:
        if not isinstance(item, dict) or set(item) != {
            "key_id",
            "public_key_pem",
            "not_before",
            "not_after",
            "revoked_at",
        }:
            raise ExportValidationError("INVALID_VERIFICATION_KEY_REGISTRY")
        try:
            key_id = str(item["key_id"])
            not_before = datetime.fromisoformat(str(item["not_before"]).replace("Z", "+00:00"))
            not_after = datetime.fromisoformat(str(item["not_after"]).replace("Z", "+00:00"))
            revoked = item["revoked_at"]
            revoked_at = (
                None
                if revoked is None
                else datetime.fromisoformat(str(revoked).replace("Z", "+00:00"))
            )
            if key_id in keys or not_before.tzinfo is None or not_after.tzinfo is None:
                raise ValueError
            keys[key_id] = VerificationKey(
                key_id, str(item["public_key_pem"]).encode(), not_before, not_after, revoked_at
            )
        except (TypeError, ValueError):
            raise ExportValidationError("INVALID_VERIFICATION_KEY_REGISTRY") from None
    return InMemoryVerificationKeyResolver(keys)
