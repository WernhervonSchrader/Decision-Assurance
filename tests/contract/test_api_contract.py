from fastapi.testclient import TestClient

from conftest import headers


def test_health_endpoints(client: TestClient) -> None:
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").status_code == 200


def test_missing_authentication_is_localized(client: TestClient) -> None:
    response = client.get("/v1/decisions/D-1", headers={"Accept-Language": "de"})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
    assert response.json()["message"] == "Authentifizierung erforderlich."
    assert response.json()["correlation_id"]


def test_create_is_strict_and_idempotent(client: TestClient, decision: dict) -> None:
    first = client.post("/v1/decisions", headers=headers("a-generator", "create-1"), json=decision)
    second = client.post("/v1/decisions", headers=headers("a-generator", "create-1"), json=decision)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    manipulated = dict(decision, title="changed")
    assert client.post("/v1/decisions", headers=headers("a-generator", "create-1"), json=manipulated).status_code == 409


def test_unknown_fields_and_actor_spoofing_are_rejected(client: TestClient, decision: dict) -> None:
    assert client.post("/v1/decisions", headers=headers("a-generator", "x1"), json=dict(decision, tenant_id="tenant-b")).status_code == 422
    spoofed = dict(decision, created_by={"id":"someone-else","role":"GENERATOR","kind":"AGENT"})
    assert client.post("/v1/decisions", headers=headers("a-generator", "x2"), json=spoofed).status_code == 403


def test_cross_tenant_case_is_not_enumerable(client: TestClient, decision: dict) -> None:
    assert client.post("/v1/decisions", headers=headers("a-generator", "x3"), json=decision).status_code == 201
    assert client.get(f"/v1/decisions/{decision['decision_id']}", headers=headers("b-generator")).status_code == 404


def test_validator_can_evaluate_and_auditor_can_read(client: TestClient, decision: dict) -> None:
    decision_id = decision["decision_id"]
    client.post("/v1/decisions", headers=headers("a-generator", "x4"), json=decision)
    evaluated = client.post(f"/v1/decisions/{decision_id}/evaluate", headers=headers("a-validator", "eval-1"))
    assert evaluated.status_code == 200
    assert evaluated.json()["outcome"] == "PASS"
    assert client.get(f"/v1/decisions/{decision_id}/report", headers=headers("a-auditor")).json()["outcome"] == "PASS"
    events = client.get(f"/v1/decisions/{decision_id}/audit", headers=headers("a-auditor")).json()["items"]
    assert [event["event_type"] for event in events] == ["decision.created", "decision.evaluated"]


def test_wrong_role_and_agent_approval_fail_closed(client: TestClient, decision: dict) -> None:
    decision_id = decision["decision_id"]
    client.post("/v1/decisions", headers=headers("a-generator", "x5"), json=decision)
    assert client.post(f"/v1/decisions/{decision_id}/evaluate", headers=headers("a-generator", "eval-x")).status_code == 403
    client.post(f"/v1/decisions/{decision_id}/evaluate", headers=headers("a-validator", "eval-2"))
    client.post(f"/v1/decisions/{decision_id}/transitions", headers=headers("a-validator", "tr-1"), json={"target":"VALIDATION"})
    client.post(f"/v1/decisions/{decision_id}/transitions", headers=headers("a-validator", "tr-2"), json={"target":"REVIEW"})
    response = client.post(f"/v1/decisions/{decision_id}/transitions", headers=headers("a-agent-approver", "tr-3"), json={"target":"APPROVED"})
    assert response.status_code == 409
    assert "HUMAN_APPROVER_REQUIRED" in response.json()["details"]["reason_codes"]


def test_idempotency_key_is_required_for_writes(client: TestClient, decision: dict) -> None:
    response = client.post("/v1/decisions", headers=headers("a-generator"), json=decision)
    assert response.status_code == 422
