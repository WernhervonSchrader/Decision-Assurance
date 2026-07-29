from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from ..identity import StaticTokenAuthenticator
from ..intake.repository import SqliteIntakeRepository
from ..intake.verification import InMemoryPolicyRegistry
from ..repositories.sqlite import SqliteDecisionRepository
from .app import create_app


def generate(path: Path) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Path(temporary) / "openapi.db"
        repository = SqliteDecisionRepository(database)
        intake_repository = SqliteIntakeRepository(database)
        repository.initialize()
        intake_repository.initialize()
        app = create_app(
            repository,
            StaticTokenAuthenticator({}),
            intake_repository,
            InMemoryPolicyRegistry({}),
        )
        path.write_text(
            json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export deterministic OpenAPI JSON")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    generate(args.output)


if __name__ == "__main__":
    main()
