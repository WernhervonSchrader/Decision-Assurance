from pathlib import Path

from fastapi.testclient import TestClient

from decision_assurance.api.app import create_app
from decision_assurance.identity import ActorKind, Identity, Role, StaticTokenAuthenticator
from decision_assurance.intake.contracts import PolicyContext
from decision_assurance.intake.repository import SqliteIntakeRepository
from decision_assurance.intake.verification import InMemoryPolicyRegistry
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.tenancy import TenantContext


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
        for role in (Role.GENERATOR, Role.VALIDATOR)
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


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": "test-key"}


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
    compiled = api.post("/v1/intakes/I-1/compile", headers=headers("a-validator"))
    assert compiled.status_code == 201
    assert compiled.json()["decision_outcome"] is None
