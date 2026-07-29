from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


class ContractValidationError(ValueError):
    pass


class ContractValidator:
    def __init__(self, schema_directory: Path | None = None):
        self.schema_directory = schema_directory or Path(__file__).parent / "schemas"

    def validate(self, contract: str, instance: dict[str, Any]) -> None:
        path = self.schema_directory / f"{contract}.schema.json"
        if not path.is_file():
            raise ContractValidationError(f"Unknown contract schema: {contract}")
        schema = json.loads(path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
        if errors:
            descriptions = "; ".join(
                f"{'/'.join(map(str, error.path)) or '<root>'}: {error.message}" for error in errors
            )
            raise ContractValidationError(descriptions)
