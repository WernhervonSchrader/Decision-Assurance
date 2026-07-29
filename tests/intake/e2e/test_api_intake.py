from pathlib import Path

from fastapi.testclient import TestClient

from decision_assurance.api.app import create_app
from decision_assurance.identity import ActorKind, Identity, Role, StaticTokenAuthenticator
from decision_assurance.intake.contracts import PolicyContext
from decision_assurance.intake.repository import SqliteIntakeRepository
from decision_assurance.intake.verification import InMemoryPolicyRegistry
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.tenancy import TenantContext
from decision_assurance.validation import ContractValidator


def client(tmp_path: Path) -> TestClient:
    database = tmp_path / "api.db"
    decisions = SqliteDecisionRepository(database)
    intakes = SqliteIntakeRepository(database)
    decisions.initialize()
    intakes.initialize()
    identities = {
        f"{tenant}-{role.value.lower()}": Identity(
            f"{tenant}-{role.value.lower()}", TenantContext(tenant), role, ActorKind.HUMAN
        )
        for tenant in ("a", "b")
        for role in (Role.GENERATOR, Role.VALIDATOR, Role.AUDITOR)
    }
    policy = PolicyContext("P-1", "1", "2026-01-01", "10", "25", 24, "50000")
    return TestClient(
        create_app(
            decisions,
            StaticTokenAuthenticator(identities),
            intakes,
            InMemoryPolicyRegistry({"a": policy, "b": policy}),
        )
    )


def headers(token: str, key: str = "test-key") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key}


def test_same_intake_id_is_fully_isolated_between_tenants(tmp_path: Path) -> None:
    api = client(tmp_path)
    for tenant, amount in (("a", "40,000"), ("b", "45,000")):
        response = api.post(
            "/v1/intakes",
            headers=headers(f"{tenant}-generator"),
            json={
                "schema_version": "0.3.0",
                "intake_id": "I-shared",
                "raw_input": f"Quote {amount} EUR, 8% discount and 30% margin.",
                "locale": "en",
            },
        )
        assert response.status_code == 201
    a_record = api.get("/v1/intakes/I-shared", headers=headers("a-generator")).json()
    b_record = api.get("/v1/intakes/I-shared", headers=headers("b-generator")).json()
    assert a_record["raw_input"] != b_record["raw_input"]
    assert "45,000" not in str(a_record)
    assert "40,000" not in str(b_record)


def test_tenant_is_rejected_from_client_payload_and_compile_is_outcome_free(tmp_path: Path) -> None:
    api = client(tmp_path)
    invalid = api.post(
        "/v1/intakes",
        headers=headers("a-generator"),
        json={
            "schema_version": "0.3.0",
            "intake_id": "I-1",
            "raw_input": "Quote 40,000 EUR, 8% discount and 30% margin.",
            "locale": "en",
            "tenant_id": "b",
        },
    )
    assert invalid.status_code == 422
    created = api.post(
        "/v1/intakes",
        headers=headers("a-generator"),
        json={
            "schema_version": "0.3.0",
            "intake_id": "I-1",
            "raw_input": "Quote 40,000 EUR, 8% discount and 30% margin.",
            "locale": "en",
        },
    )
    assert created.json()["contract_ready"] is True
    ContractValidator().validate("intake/intake-record", created.json())
    compiled = api.post("/v1/intakes/I-1/compile", headers=headers("a-validator"))
    assert compiled.status_code == 201
    assert compiled.json()["decision_outcome"] is None


def test_intake_audit_and_replays_are_idempotent(tmp_path: Path) -> None:
    api = client(tmp_path)
    payload = {
        "schema_version": "0.3.0",
        "intake_id": "I-audit",
        "raw_input": "Quote 40,000 EUR, 8% discount and 30% margin.",
        "locale": "en",
    }
    first = api.post("/v1/intakes", headers=headers("a-generator", "create-audit"), json=payload)
    replay = api.post("/v1/intakes", headers=headers("a-generator", "create-audit"), json=payload)
    assert first.json() == replay.json()
    audit = api.get("/v1/intakes/I-audit/audit", headers=headers("a-auditor")).json()
    assert [item["event_type"] for item in audit["items"]] == [
        "intake.extracted",
        "intake.readiness-determined",
    ]
    assert api.get("/v1/intakes/I-audit/audit", headers=headers("b-auditor")).status_code == 404


def test_intake_rejects_non_json_content_type(tmp_path: Path) -> None:
    response = client(tmp_path).post(
        "/v1/intakes",
        headers={"Authorization": "Bearer a-generator", "Content-Type": "text/plain"},
        content="not json",
    )
    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_confirmation_replay_creates_one_confirmation_and_audit_event(tmp_path: Path) -> None:
    api = client(tmp_path)
    created = api.post(
        "/v1/intakes",
        headers=headers("a-generator", "create-confirm"),
        json={
            "schema_version": "0.3.0",
            "intake_id": "I-confirm",
            "raw_input": (
                "Quote 40,000 EUR, 8% discount and 30% margin. Management approval is claimed."
            ),
            "locale": "en",
        },
    ).json()
    fact_id = next(
        item["fact_id"]
        for item in created["verification"]["candidates"]
        if item["fact_type"] == "APPROVAL_CLAIM"
    )
    payload = {
        "fact_id": fact_id,
        "action": "CONFIRM",
        "new_value": None,
        "reason": "checked approval record",
    }
    first = api.post(
        "/v1/intakes/I-confirm/confirmations",
        headers=headers("a-validator", "confirm-once"),
        json=payload,
    )
    replay = api.post(
        "/v1/intakes/I-confirm/confirmations",
        headers=headers("a-validator", "confirm-once"),
        json=payload,
    )
    assert first.json() == replay.json()
    assert len(first.json()["confirmations"]) == 1
    audit = api.get("/v1/intakes/I-confirm/audit", headers=headers("a-auditor")).json()
    assert len(audit["items"]) == 3
