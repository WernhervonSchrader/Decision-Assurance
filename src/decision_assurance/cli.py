from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .engine import DecisionAssuranceEngine


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assess a Decision Assurance JSON request")
    parser.add_argument("input", type=Path, help="JSON request or DATS scenario")
    args = parser.parse_args(argv)
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = DecisionAssuranceEngine().assess(payload)
    print(json.dumps(result.report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
