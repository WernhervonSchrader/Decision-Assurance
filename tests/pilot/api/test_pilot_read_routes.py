from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from decision_assurance.api.app import create_app
from decision_assurance.identity import ActorKind, Identity, Role, StaticTokenAuthenticator
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.tenancy import TenantContext

ROOT = Path(__file__).parents[3]


def _document(decision_id: str, actor: str) -> dict[str, object]:
    value = json.loads(
        (ROOT / "examples" / "decision-cases" / "low-risk-pass.json").read_text(encoding="utf-8")
    )
    value["decision_id"] = decision_id
    value["created_by"] = {"id": actor, "role": "GENERATOR", "kind": "HUMAN"}
    return value


def test_session_and_case_list_are_derived_from_authenticated_tenant(tmp_path: Path) -> None:
    repository = SqliteDecisionRepository(tmp_path / "pilot.db")
    repository.initialize()
    tenant_a = TenantContext("tenant-a")
    tenant_b = TenantContext("tenant-b")
    repository.create_decision(tenant_a, _document("a-1", "alice"))
    repository.create_decision(tenant_a, _document("a-2", "alice"))
    repository.create_decision(tenant_b, _document("b-1", "bob"))
    identities = {
        "a": Identity("alice", tenant_a, Role.GENERATOR, ActorKind.HUMAN),
        "b": Identity("bob", tenant_b, Role.GENERATOR, ActorKind.HUMAN),
    }
    client = TestClient(create_app(repository, StaticTokenAuthenticator(identities)))

    session = client.get("/v1/session", headers={"Authorization": "Bearer a"})
    cases = client.get("/v1/decisions?limit=10", headers={"Authorization": "Bearer a"})

    assert session.status_code == 200
    assert session.json() == {
        "actor_id": "alice",
        "tenant_id": "tenant-a",
        "actor_kind": "HUMAN",
        "roles": ["GENERATOR"],
    }
    assert cases.status_code == 200
    assert [item["decision_id"] for item in cases.json()["items"]] == ["a-2", "a-1"]
    assert all(item["decision_id"] != "b-1" for item in cases.json()["items"])
    assert "tenant_id" not in cases.json()


def test_case_list_is_bounded_and_does_not_accept_tenant_override(tmp_path: Path) -> None:
    repository = SqliteDecisionRepository(tmp_path / "pilot.db")
    repository.initialize()
    identity = Identity("alice", TenantContext("tenant-a"), Role.GENERATOR, ActorKind.HUMAN)
    client = TestClient(create_app(repository, StaticTokenAuthenticator({"a": identity})))

    assert (
        client.get("/v1/decisions?limit=101", headers={"Authorization": "Bearer a"}).status_code
        == 422
    )
    override = client.get("/v1/decisions?tenant_id=tenant-b", headers={"Authorization": "Bearer a"})
    assert override.status_code == 422
