import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from decision_assurance.api.app import create_app
from decision_assurance.identity import ActorKind, Identity, Role, StaticTokenAuthenticator
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.tenancy import TenantContext

ROOT = Path(__file__).parents[2]


@pytest.fixture
def identities() -> dict[str, Identity]:
    return {
        "a-generator": Identity(
            "generator-a", TenantContext("tenant-a"), Role.GENERATOR, ActorKind.AGENT
        ),
        "a-validator": Identity(
            "validator-a", TenantContext("tenant-a"), Role.VALIDATOR, ActorKind.HUMAN
        ),
        "a-approver": Identity(
            "approver-a", TenantContext("tenant-a"), Role.APPROVER, ActorKind.HUMAN
        ),
        "a-agent-approver": Identity(
            "agent-approver", TenantContext("tenant-a"), Role.APPROVER, ActorKind.AGENT
        ),
        "a-auditor": Identity(
            "auditor-a", TenantContext("tenant-a"), Role.AUDITOR, ActorKind.HUMAN
        ),
        "b-generator": Identity(
            "generator-b", TenantContext("tenant-b"), Role.GENERATOR, ActorKind.AGENT
        ),
    }


@pytest.fixture
def client(tmp_path: Path, identities: dict[str, Identity]) -> TestClient:
    repository = SqliteDecisionRepository(tmp_path / "api.db")
    repository.initialize()
    return TestClient(create_app(repository, StaticTokenAuthenticator(identities)))


@pytest.fixture
def decision() -> dict:
    document = json.loads(
        (ROOT / "examples" / "decision-cases" / "low-risk-pass.json").read_text(encoding="utf-8")
    )
    document["created_by"] = {"id": "generator-a", "role": "GENERATOR", "kind": "AGENT"}
    return document


def headers(token: str, key: str | None = None) -> dict[str, str]:
    result = {"Authorization": f"Bearer {token}"}
    if key:
        result["Idempotency-Key"] = key
    return result
