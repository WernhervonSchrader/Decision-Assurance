"""Generate/check the optional adapter contract; never change the normative Decision File."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from decision_assurance.strategy.contracts import ImportEnvelope

ROOT = Path(__file__).resolve().parents[2]
PATHS = [
    ROOT / "schemas/strategy/import-envelope.schema.json",
    ROOT / "src/decision_assurance/schemas/strategy/import-envelope.schema.json",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    schema = ImportEnvelope.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "urn:decision-assurance:strategy:rif-3.4-rc3:da-1"
    for path in PATHS:
        if args.write:
            path.write_text(
                json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        elif json.loads(path.read_text(encoding="utf-8")) != schema:
            raise ValueError("STRATEGY_SCHEMA_DRIFT")
    print("Optional strategy envelope schema matches both packaged and public copies")


if __name__ == "__main__":
    main()
