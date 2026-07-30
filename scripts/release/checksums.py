from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def create_checksum_manifest(artifact_dir: Path, output: Path) -> None:
    root = artifact_dir.resolve(strict=True)
    destination = output.resolve()
    if destination == root or root in destination.parents:
        raise ValueError("CHECKSUM_OUTPUT_INSIDE_ARTIFACTS")

    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise ValueError("NO_RELEASE_ARTIFACTS")
    lines = []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        relative = path.relative_to(root).as_posix()
        lines.append(f"{digest}  {relative}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    create_checksum_manifest(args.artifact_dir, args.output)


if __name__ == "__main__":
    main()
