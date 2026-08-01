from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path("scripts/security/assert_no_secret_values.py")


def test_secret_output_scanner_accepts_secret_free_outputs(tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    output = tmp_path / "output.log"
    secret.write_text("synthetic-canary-value", encoding="utf-8")
    output.write_text("bootstrap completed with redacted identity", encoding="utf-8")

    result = subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned script
        [
            sys.executable,
            str(SCRIPT),
            "--secret-file",
            str(secret),
            "--input-file",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "secret-scan-ok" in result.stdout
    assert "synthetic-canary-value" not in result.stdout + result.stderr


def test_secret_output_scanner_fails_without_echoing_detected_value(tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    output = tmp_path / "output.log"
    secret.write_text("synthetic-canary-value", encoding="utf-8")
    output.write_text("unsafe synthetic-canary-value output", encoding="utf-8")

    result = subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned script
        [
            sys.executable,
            str(SCRIPT),
            "--secret-file",
            str(secret),
            "--input-file",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "secret-scan-failed" in result.stderr
    assert "synthetic-canary-value" not in result.stdout + result.stderr


def test_secret_output_scanner_rejects_empty_secret_files(tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    output = tmp_path / "output.log"
    secret.write_text("", encoding="utf-8")
    output.write_text("output", encoding="utf-8")

    result = subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned script
        [
            sys.executable,
            str(SCRIPT),
            "--secret-file",
            str(secret),
            "--input-file",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "secret-scan-invalid-input" in result.stderr
