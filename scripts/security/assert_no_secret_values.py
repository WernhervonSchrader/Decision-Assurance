from __future__ import annotations

import argparse
import sys
from pathlib import Path

MAX_SECRET_BYTES = 4_096
MAX_INPUT_BYTES = 20_000_000


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fail if captured output contains a secret value.")
    parser.add_argument("--secret-file", action="append", required=True, type=Path)
    parser.add_argument("--input-file", action="append", required=True, type=Path)
    return parser


def _secret(path: Path) -> bytes:
    value = path.read_bytes().rstrip(b"\r\n")
    if not value or len(value) > MAX_SECRET_BYTES:
        raise ValueError("invalid secret input")
    return value


def _captured_output(path: Path) -> bytes:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("captured output too large")
    return path.read_bytes()


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        secrets = tuple(_secret(path) for path in arguments.secret_file)
        outputs = tuple(_captured_output(path) for path in arguments.input_file)
    except (OSError, ValueError):
        print("secret-scan-invalid-input", file=sys.stderr)
        return 2
    if any(secret in output for secret in secrets for output in outputs):
        print("secret-scan-failed", file=sys.stderr)
        return 1
    print(f"secret-scan-ok inputs={len(outputs)} secrets={len(secrets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
