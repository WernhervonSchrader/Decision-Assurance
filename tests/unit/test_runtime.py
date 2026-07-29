import json
from pathlib import Path

import pytest

from decision_assurance.api.runtime import load_runtime


def test_runtime_requires_explicit_configuration() -> None:
    with pytest.raises(RuntimeError, match="DA_DATABASE_PATH"):
        load_runtime({})


def test_runtime_loads_tenant_identity_from_protected_file(tmp_path: Path) -> None:
    identities = tmp_path / "identities.json"
    identities.write_text(
        json.dumps(
            {
                "test-token": {
                    "actor_id": "actor-1",
                    "tenant_id": "tenant-a",
                    "role": "GENERATOR",
                    "kind": "AGENT",
                }
            }
        ),
        encoding="utf-8",
    )
    app = load_runtime(
        {"DA_DATABASE_PATH": str(tmp_path / "api.db"), "DA_IDENTITIES_PATH": str(identities)}
    )
    assert app.title == "Decision Assurance API"
