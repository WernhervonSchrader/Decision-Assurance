from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

from .service import EXPORT_MEMBERS

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


def validate_export(content: bytes) -> ValidationReport:
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
        expected = {"manifest.json", *EXPORT_MEMBERS}
        if set(names) != expected:
            raise ExportValidationError("EXPORT_MEMBER_SET_MISMATCH")
        if sum(item.file_size for item in infos) > MAX_UNCOMPRESSED_BYTES:
            raise ExportValidationError("EXPORT_SIZE_REJECTED")
        try:
            manifest = cast(dict[str, Any], json.loads(archive.read("manifest.json")))
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError):
            raise ExportValidationError("INVALID_EXPORT_MANIFEST") from None
        _validate_manifest(manifest)
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
        return ValidationReport(
            valid=True,
            case_ref=str(manifest["case_ref"]),
            member_count=len(declared),
            export_id=str(manifest["export_id"]),
        )


def _validate_manifest(manifest: dict[str, Any]) -> None:
    resource = files("decision_assurance.schemas").joinpath("production/pilot-export.schema.json")
    schema = json.loads(resource.read_text(encoding="utf-8"))
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(manifest)
    )
    if errors:
        raise ExportValidationError("INVALID_EXPORT_MANIFEST")


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
        prior_hashes: set[str] = set()
        for event in cast(list[dict[str, object]], events):
            previous = event.get("previous_event_hash")
            if previous is not None and previous not in prior_hashes:
                raise ExportValidationError("INVALID_EXPORT_AUDIT_CHAIN")
            prior_hashes.add(_prefixed_hash(event))

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline Decision Assurance pilot export validator"
    )
    parser.add_argument("archive", type=Path)
    arguments = parser.parse_args()
    if arguments.archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise SystemExit("EXPORT_SIZE_REJECTED")
    try:
        report = validate_export(arguments.archive.read_bytes())
    except (OSError, ExportValidationError) as error:
        raise SystemExit(str(error)) from None
    print(
        json.dumps(
            {
                "valid": report.valid,
                "case_ref": report.case_ref,
                "export_id": report.export_id,
                "member_count": report.member_count,
            },
            sort_keys=True,
        )
    )
