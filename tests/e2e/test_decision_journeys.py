import json
from pathlib import Path

from fastapi.testclient import TestClient

from decision_assurance.api.app import create_app
from decision_assurance.identity import ActorKind, Identity, Role, StaticTokenAuthenticator
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.tenancy import TenantContext


ROOT = Path(__file__).parents[2]


def test_two_tenant_approved_and_blocked_journeys(tmp_path: Path) -> None:
    identities = {
        "a-gen": Identity("generator-a", TenantContext("tenant-a"), Role.GENERATOR, ActorKind.AGENT),
        "a-val": Identity("validator-a", TenantContext("tenant-a"), Role.VALIDATOR, ActorKind.HUMAN),
        "a-app": Identity("approver-a", TenantContext("tenant-a"), Role.APPROVER, ActorKind.HUMAN),
        "a-aud": Identity("auditor-a", TenantContext("tenant-a"), Role.AUDITOR, ActorKind.HUMAN),
        "b-gen": Identity("generator-b", TenantContext("tenant-b"), Role.GENERATOR, ActorKind.AGENT),
        "b-val": Identity("validator-b", TenantContext("tenant-b"), Role.VALIDATOR, ActorKind.HUMAN),
        "b-aud": Identity("auditor-b", TenantContext("tenant-b"), Role.AUDITOR, ActorKind.HUMAN),
    }
    repository = SqliteDecisionRepository(tmp_path / "e2e.db")
    repository.initialize()
    client = TestClient(create_app(repository, StaticTokenAuthenticator(identities)))

    def auth(token: str, key: str | None = None, locale: str = "en") -> dict[str, str]:
        result = {"Authorization": f"Bearer {token}", "Accept-Language": locale}
        if key:
            result["Idempotency-Key"] = key
        return result

    approved = json.loads((ROOT / "examples" / "decision-cases" / "low-risk-pass.json").read_text(encoding="utf-8"))
    approved["created_by"] = {"id":"generator-a","role":"GENERATOR","kind":"AGENT"}
    approved["review_requirements"] = []
    decision_id = approved["decision_id"]
    assert client.post("/v1/decisions", headers=auth("a-gen", "a-create"), json=approved).status_code == 201
    assert client.post(f"/v1/decisions/{decision_id}/evaluate", headers=auth("a-val", "a-eval")).json()["outcome"] == "PASS"
    assert client.post(f"/v1/decisions/{decision_id}/transitions", headers=auth("a-val", "a-valid"), json={"target":"VALIDATION"}).status_code == 200
    assert client.post(f"/v1/decisions/{decision_id}/transitions", headers=auth("a-val", "a-review"), json={"target":"REVIEW"}).status_code == 200
    terminal = client.post(f"/v1/decisions/{decision_id}/transitions", headers=auth("a-app", "a-approve"), json={"target":"APPROVED"})
    assert terminal.status_code == 200
    assert terminal.json()["status"] == "APPROVED"

    blocked = json.loads((ROOT / "examples" / "decision-cases" / "hard-constraint-block.json").read_text(encoding="utf-8"))
    blocked["decision_id"] = decision_id
    blocked["created_by"] = {"id":"generator-b","role":"GENERATOR","kind":"AGENT"}
    assert client.post("/v1/decisions", headers=auth("b-gen", "b-create", "de"), json=blocked).status_code == 201
    assert client.post(f"/v1/decisions/{decision_id}/evaluate", headers=auth("b-val", "b-eval", "de")).json()["outcome"] == "BLOCK"
    terminal = client.post(f"/v1/decisions/{decision_id}/transitions", headers=auth("b-val", "b-block", "de"), json={"target":"BLOCKED"})
    assert terminal.status_code == 200
    assert terminal.json()["status"] == "BLOCKED"

    a_events = client.get(f"/v1/decisions/{decision_id}/audit", headers=auth("a-aud")).json()["items"]
    b_events = client.get(f"/v1/decisions/{decision_id}/audit", headers=auth("b-aud")).json()["items"]
    assert [event["to_status"] for event in a_events] == ["DRAFT", "DRAFT", "VALIDATION", "REVIEW", "APPROVED"]
    assert [event["to_status"] for event in b_events] == ["DRAFT", "DRAFT", "BLOCKED"]
    assert all(event["tenant_id"] == "tenant-a" for event in a_events)
    assert all(event["tenant_id"] == "tenant-b" for event in b_events)


def test_oversized_request_fails_before_processing(tmp_path: Path) -> None:
    repository = SqliteDecisionRepository(tmp_path / "limits.db")
    repository.initialize()
    client = TestClient(create_app(repository, StaticTokenAuthenticator({})))
    response = client.post("/v1/decisions", content=b"x" * 1_048_577)
    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"
