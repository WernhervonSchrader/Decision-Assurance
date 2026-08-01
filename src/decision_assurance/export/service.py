from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from ..authorization import Permission, authorize
from ..identity import Identity
from .ports import ExportRepository
from .signing import ExportSigner

EXPORT_MEMBERS = (
    "decision/decision-file.json",
    "decision/assurance-report.json",
    "intake/intake-records.json",
    "research/research-runs.json",
    "research/sources.json",
    "research/evidence.json",
    "audit/decision-events.json",
    "audit/intake-events.json",
    "audit/research-events.json",
    "audit/lifecycle-events.json",
)
_SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "refresh_token",
        "id_token",
        "authorization",
        "password",
        "secret",
        "api_key",
        "prompt",
        "code_verifier",
    }
)


class ExportRejected(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ExportArchive:
    content: bytes
    filename: str = "decision-assurance-pilot-export.zip"
    media_type: str = "application/zip"


class PilotExportService:
    def __init__(
        self,
        repository: ExportRepository,
        *,
        version: str,
        commit_sha: str,
        policy_versions: Mapping[str, str],
        signer: ExportSigner | None = None,
        event_schema_version: str = "0.8.0",
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        if not version.strip() or len(commit_sha) not in {40, 64}:
            raise ValueError("INVALID_EXPORT_BUILD_METADATA")
        self._repository = repository
        self._version = version
        self._commit_sha = commit_sha
        self._policy_versions = dict(policy_versions)
        self._signer = signer
        self._event_schema_version = event_schema_version
        self._clock = clock

    def build(self, identity: Identity, decision_id: str) -> ExportArchive:
        authorize(identity, Permission.PILOT_EXPORT)
        snapshot = self._repository.snapshot(identity.tenant, decision_id)
        if snapshot is None:
            raise ExportRejected("CASE_NOT_FOUND")
        if set(snapshot) != set(EXPORT_MEMBERS):
            raise ExportRejected("INCOMPLETE_EXPORT_SNAPSHOT")
        if _contains_sensitive_field(snapshot):
            raise ExportRejected("SENSITIVE_EXPORT_FIELD")
        members = {name: _canonical_json(snapshot[name]) for name in EXPORT_MEMBERS}
        generated_at = self._clock().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        export_seed = _canonical_json(
            {
                "tenant": identity.tenant.tenant_id,
                "case": decision_id,
                "generated_at": generated_at,
                "commit": self._commit_sha,
            }
        )
        schema_version = "0.9.0" if self._signer is not None else "0.8.0"
        manifest: dict[str, object] = {
            "schema_version": schema_version,
            "export_id": "export-" + hashlib.sha256(export_seed).hexdigest()[:24],
            "case_ref": decision_id,
            "generated_at": generated_at,
            "software": {"version": self._version, "commit_sha": self._commit_sha},
            "policy_versions": self._policy_versions,
            "members": [
                {
                    "path": name,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "bytes": len(content),
                }
                for name, content in members.items()
            ],
        }
        if self._signer is not None:
            manifest.update(
                {
                    "tenant_id": identity.tenant.tenant_id,
                    "decision_id": decision_id,
                    "event_schema_version": self._event_schema_version,
                }
            )
        manifest_bytes = _canonical_json(manifest)
        output = io.BytesIO()
        with zipfile.ZipFile(
            output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            _write_member(archive, "manifest.json", manifest_bytes)
            if self._signer is not None:
                _write_member(
                    archive,
                    "signature.json",
                    _canonical_json(self._signer.sign(manifest_bytes).as_dict()),
                )
            for name, content in members.items():
                _write_member(archive, name, content)
        return ExportArchive(output.getvalue())


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _write_member(archive: zipfile.ZipFile, name: str, content: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100600 << 16
    info.create_system = 3
    archive.writestr(info, content, compresslevel=9)


def _contains_sensitive_field(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if normalized in _SENSITIVE_KEYS or normalized.endswith("_secret"):
                return True
            if _contains_sensitive_field(item):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_sensitive_field(item) for item in value)
    return False
