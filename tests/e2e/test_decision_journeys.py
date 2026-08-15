import json
from pathlib import Path

from fastapi.testclient import TestClient

from decision_assurance.api.app import create_app
from decision_assurance.audit import payload_hash
from decision_assurance.decision_file import bind_canonical_action, validate_semantics
from decision_assurance.identity import ActorKind, Identity, Role, StaticTokenAuthenticator
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.tenancy import TenantContext

ROOT = Path(__file__).parents[2]


def test_two_tenant_approved_and_blocked_journeys(tmp_path: Path) -> None:
    identities = {
        "a-gen": Identity(
            "generator-a", TenantContext("tenant-a"), Role.GENERATOR, ActorKind.AGENT
        ),
        "a-val": Identity(
            "validator-a", TenantContext("tenant-a"), Role.VALIDATOR, ActorKind.HUMAN
        ),
        "a-app": Identity("approver-a", TenantContext("tenant-a"), Role.APPROVER, ActorKind.HUMAN),
        "a-aud": Identity("auditor-a", TenantContext("tenant-a"), Role.AUDITOR, ActorKind.HUMAN),
        "b-gen": Identity(
            "generator-b", TenantContext("tenant-b"), Role.GENERATOR, ActorKind.AGENT
        ),
        "b-val": Identity(
            "validator-b", TenantContext("tenant-b"), Role.VALIDATOR, ActorKind.HUMAN
        ),
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

    approved = json.loads(
        (ROOT / "examples" / "decision-cases" / "low-risk-pass.json").read_text(encoding="utf-8")
    )
    approved["created_by"] = {"id": "generator-a", "role": "GENERATOR", "kind": "AGENT"}
    approved["review_requirements"] = []
    decision_id = approved["decision_id"]
    assert (
        client.post("/v1/decisions", headers=auth("a-gen", "a-create"), json=approved).status_code
        == 201
    )
    assert (
        client.post(
            f"/v1/decisions/{decision_id}/evaluate", headers=auth("a-val", "a-eval")
        ).json()["outcome"]
        == "PASS"
    )
    assert (
        client.post(
            f"/v1/decisions/{decision_id}/transitions",
            headers=auth("a-val", "a-valid"),
            json={"target": "VALIDATION"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/v1/decisions/{decision_id}/transitions",
            headers=auth("a-val", "a-review"),
            json={"target": "REVIEW"},
        ).status_code
        == 200
    )
    terminal = client.post(
        f"/v1/decisions/{decision_id}/transitions",
        headers=auth("a-app", "a-approve"),
        json={"target": "APPROVED"},
    )
    assert terminal.status_code == 200
    assert terminal.json()["status"] == "APPROVED"

    blocked = json.loads(
        (ROOT / "examples" / "decision-cases" / "hard-constraint-block.json").read_text(
            encoding="utf-8"
        )
    )
    blocked["decision_id"] = decision_id
    blocked["created_by"] = {"id": "generator-b", "role": "GENERATOR", "kind": "AGENT"}
    assert (
        client.post(
            "/v1/decisions", headers=auth("b-gen", "b-create", "de"), json=blocked
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/v1/decisions/{decision_id}/evaluate", headers=auth("b-val", "b-eval", "de")
        ).json()["outcome"]
        == "BLOCK"
    )
    terminal = client.post(
        f"/v1/decisions/{decision_id}/transitions",
        headers=auth("b-val", "b-block", "de"),
        json={"target": "BLOCKED"},
    )
    assert terminal.status_code == 200
    assert terminal.json()["status"] == "BLOCKED"

    a_events = client.get(f"/v1/decisions/{decision_id}/audit", headers=auth("a-aud")).json()[
        "items"
    ]
    b_events = client.get(f"/v1/decisions/{decision_id}/audit", headers=auth("b-aud")).json()[
        "items"
    ]
    assert [event["to_status"] for event in a_events] == [
        "DRAFT",
        "DRAFT",
        "VALIDATION",
        "REVIEW",
        "APPROVED",
    ]
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


def test_authenticated_approver_binds_action_and_idempotent_replay(tmp_path: Path) -> None:
    identities = {
        "gen": Identity("generator", TenantContext("tenant-a"), Role.GENERATOR, ActorKind.AGENT),
        "val": Identity("validator", TenantContext("tenant-a"), Role.VALIDATOR, ActorKind.HUMAN),
        "app": Identity("approver", TenantContext("tenant-a"), Role.APPROVER, ActorKind.HUMAN),
    }
    repository = SqliteDecisionRepository(tmp_path / "action-approval.db")
    repository.initialize()
    client = TestClient(create_app(repository, StaticTokenAuthenticator(identities)))

    def headers(token: str, key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Idempotency-Key": key}

    document = json.loads(
        (ROOT / "examples" / "decision-cases" / "low-risk-pass.json").read_text(encoding="utf-8")
    )
    document["decision_id"] = "ACTION-APPROVAL-E2E-001"
    document["created_by"] = {"id": "generator", "role": "GENERATOR", "kind": "AGENT"}
    document["requested_by"] = {"id": "requester", "role": "OWNER", "kind": "HUMAN"}
    document["canonical_action"] = bind_canonical_action(
        {
            "action_id": "ACTION-1",
            "action_type": "quote.publish",
            "effect": "Publish the approved quote.",
            "target": {"type": "sales-quote", "id": "QUOTE-1"},
            "parameters": {"amount": "40000.00", "currency": "EUR"},
            "reversibility_class": "EXTERNALLY_REVERSIBLE",
            "tenant_id": "tenant-a",
            "execution_context_hash": "sha256:" + "a" * 64,
        }
    )
    decision_id = document["decision_id"]

    assert (
        client.post("/v1/decisions", headers=headers("gen", "create"), json=document).status_code
        == 201
    )
    assert (
        client.post(
            f"/v1/decisions/{decision_id}/evaluate", headers=headers("val", "evaluate")
        ).status_code
        == 200
    )
    for target, key in (("VALIDATION", "validate"), ("REVIEW", "review")):
        assert (
            client.post(
                f"/v1/decisions/{decision_id}/transitions",
                headers=headers("val", key),
                json={"target": target},
            ).status_code
            == 200
        )

    approval_response = client.post(
        f"/v1/decisions/{decision_id}/transitions",
        headers=headers("app", "approve"),
        json={"target": "APPROVED"},
    )
    assert approval_response.status_code == 200
    approved = approval_response.json()
    approval = approved["approvals"][0]
    assert approved["status"] == "APPROVED"
    assert approved["review_requirements"][0]["satisfied"] is True
    assert approval["approver"] == {"id": "approver", "role": "APPROVER", "kind": "HUMAN"}
    assert approval["action_digest"] == approved["canonical_action"]["canonical_digest"]
    assert approval["approval_digest"].startswith("sha256:")
    assert len(approval["nonce"]) >= 22
    assert approved["audit_events"][-1]["payload_hash"] == payload_hash(
        {
            "from": "REVIEW",
            "to": "APPROVED",
            "actor": approval["approver"],
            "approval_digests": [approval["approval_digest"]],
        }
    )
    validate_semantics(approved)

    replay = client.post(
        f"/v1/decisions/{decision_id}/transitions",
        headers=headers("app", "approve"),
        json={"target": "APPROVED"},
    )
    assert replay.status_code == 200
    assert replay.json()["approvals"] == approved["approvals"]


def test_canonical_action_cannot_cross_authenticated_tenant(tmp_path: Path) -> None:
    identity = Identity("generator", TenantContext("tenant-a"), Role.GENERATOR, ActorKind.AGENT)
    repository = SqliteDecisionRepository(tmp_path / "cross-tenant-action.db")
    repository.initialize()
    client = TestClient(create_app(repository, StaticTokenAuthenticator({"gen": identity})))
    document = json.loads(
        (ROOT / "examples" / "decision-cases" / "low-risk-pass.json").read_text(encoding="utf-8")
    )
    document["created_by"] = {"id": "generator", "role": "GENERATOR", "kind": "AGENT"}
    document["canonical_action"] = bind_canonical_action(
        {
            "action_id": "ACTION-CROSS-TENANT",
            "action_type": "quote.publish",
            "effect": "Publish a quote.",
            "target": {"type": "sales-quote", "id": "QUOTE-1"},
            "parameters": {},
            "reversibility_class": "REVERSIBLE",
            "tenant_id": "tenant-b",
            "execution_context_hash": "sha256:" + "a" * 64,
        }
    )

    response = client.post(
        "/v1/decisions",
        headers={"Authorization": "Bearer gen", "Idempotency-Key": "cross-tenant"},
        json=document,
    )
    assert response.status_code == 403
    assert response.json()["details"]["reason_code"] == "CROSS_TENANT_ACTION"
