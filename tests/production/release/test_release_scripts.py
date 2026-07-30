from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.release.checksums import create_checksum_manifest


def test_checksum_manifest_is_deterministic(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "b.txt").write_text("bravo", encoding="utf-8")
    (artifact_dir / "a.txt").write_text("alpha", encoding="utf-8")
    output = tmp_path / "SHA256SUMS"

    create_checksum_manifest(artifact_dir, output)

    assert output.read_text(encoding="utf-8").splitlines() == [
        f"{hashlib.sha256(b'alpha').hexdigest()}  a.txt",
        f"{hashlib.sha256(b'bravo').hexdigest()}  b.txt",
    ]


def test_checksum_manifest_rejects_output_inside_artifacts(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "a.txt").write_text("alpha", encoding="utf-8")

    with pytest.raises(ValueError, match="CHECKSUM_OUTPUT_INSIDE_ARTIFACTS"):
        create_checksum_manifest(artifact_dir, artifact_dir / "SHA256SUMS")
