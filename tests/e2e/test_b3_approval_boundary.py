"""B3 regressions exercise authenticated HTTP through real SQLite persistence."""

from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest
from fastapi.testclient import TestClient

from decision_assurance.api.app import create_app
from decision_assurance.audit import payload_hash
from decision_assurance.decision_file import (
    bind_approval,
    bind_canonical_action,
    validate_semantics,
)
from decision_assurance.identity import ActorKind, Identity, Role, StaticTokenAuthenticator
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.tenancy import TenantContext
from decision_assurance.validation import ContractValidator

ROOT = Path(__file__).parents[2]
TENANT = TenantContext("tenant-a")


def document() -> dict[str, Any]:
    result = json.loads((ROOT / "examples/decision-cases/low-risk-pass.json").read_text())
    result["created_by"] = {"id": "generator", "role": "GENERATOR", "kind": "HUMAN"}
    return result


def headers(token: str, key: str = "key", locale: str = "en") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key, "Accept-Language": locale}


@pytest.fixture
def boundary(tmp_path: Path) -> tuple[TestClient, SqliteDecisionRepository]:
    identities = {
        "gen": Identity("generator", TENANT, Role.GENERATOR, ActorKind.HUMAN),
        "val": Identity("validator", TENANT, Role.VALIDATOR, ActorKind.HUMAN),
        "app": Identity("approver", TENANT, Role.APPROVER, ActorKind.HUMAN),
        "agent": Identity("agent", TENANT, Role.APPROVER, ActorKind.AGENT),
        "service": Identity("service", TENANT, Role.APPROVER, ActorKind.SERVICE),
        "admin": Identity("admin", TENANT, Role.TENANT_ADMIN, ActorKind.HUMAN),
        "self": Identity("generator", TENANT, Role.APPROVER, ActorKind.HUMAN),
        "requester": Identity("sales-requester", TENANT, Role.APPROVER, ActorKind.HUMAN),
        "validator-app": Identity("validator", TENANT, Role.APPROVER, ActorKind.HUMAN),
        "other": Identity("approver", TenantContext("tenant-b"), Role.APPROVER, ActorKind.HUMAN),
    }
    repository = SqliteDecisionRepository(tmp_path / "b3.db")
    repository.initialize()
    return TestClient(create_app(repository, StaticTokenAuthenticator(identities))), repository


def to_review(client: TestClient) -> dict[str, Any]:
    body = document()
    created = client.post("/v1/decisions", json=body, headers=headers("gen"))
    assert created.status_code == 201
    path = f"/v1/decisions/{body['decision_id']}"
    assert (
        client.post(path + "/evaluate", headers=headers("val", "eval")).json()["outcome"] == "PASS"
    )
    for target in ("VALIDATION", "REVIEW"):
        response = client.post(
            path + "/transitions", json={"target": target}, headers=headers("val", target)
        )
        assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("locale", ["de", "en"])
@pytest.mark.parametrize("status", ["VALIDATION", "REVIEW", "APPROVED", "BLOCKED"])
def test_import_cannot_assign_lifecycle(boundary, status, locale):  # type: ignore[no-untyped-def]
    client, repository = boundary
    body = document()
    body["status"] = status
    # This is formally valid input; schema validation alone does not authorize it.
    ContractValidator().validate("decision-file", body)
    validate_semantics(body)
    response = client.post("/v1/decisions", json=body, headers=headers("gen", locale=locale))
    assert response.status_code == 422
    assert repository.get_decision(TENANT, body["decision_id"]) is None


@pytest.mark.parametrize("valid_digest", [True, False])
@pytest.mark.parametrize("with_action", [True, False])
def test_fabricated_human_approval_is_rejected(boundary, valid_digest, with_action):  # type: ignore[no-untyped-def]
    client, repository = boundary
    body = document()
    if with_action:
        body["canonical_action"] = bind_canonical_action(
            {
                "action_id": "ACTION-B3",
                "action_type": "quote.publish",
                "effect": "Publish quote",
                "target": {"type": "quote", "id": "Q1"},
                "parameters": {"amount": "40000"},
                "reversibility_class": "REVERSIBLE",
                "tenant_id": "tenant-a",
                "execution_context_hash": "sha256:" + "a" * 64,
            }
        )
    body["status"] = "APPROVED"
    body["decision_outcome"] = "PASS"
    body["review_requirements"][0]["satisfied"] = True
    body["approvals"] = [
        bind_approval(
            body,
            {
                "requirement_ref": "APPROVAL-1",
                "approver": {"id": "victim-human", "role": "APPROVER", "kind": "HUMAN"},
                "decision": "APPROVE",
                "decided_at": "2026-10-31T10:00:00Z",
                "action_digest": body["canonical_action"]["canonical_digest"]
                if with_action
                else None,
                "nonce": "attacker-computed-nonce-000001",
            },
        )
    ]
    if valid_digest:
        ContractValidator().validate("decision-file", body)
        validate_semantics(body)
    else:
        body["approvals"][0]["approval_digest"] = "sha256:" + "0" * 64
    assert client.post("/v1/decisions", json=body, headers=headers("gen")).status_code == 422
    assert repository.get_decision(TENANT, body["decision_id"]) is None


@pytest.mark.parametrize(
    "field",
    [
        "decision_outcome",
        "validation_results",
        "outcome_reasons",
        "review_requirements",
        "audit_events",
    ],
)
def test_draft_cannot_smuggle_server_history(boundary, field):  # type: ignore[no-untyped-def]
    client, repository = boundary
    body = document()
    if field == "decision_outcome":
        body[field] = "PASS"
    elif field == "validation_results":
        body[field] = [
            {
                "validator": {"id": "fake", "role": "VALIDATOR", "kind": "SERVICE"},
                "result": "PASS",
                "reason_codes": [],
                "validated_at": body["created_at"],
            }
        ]
    elif field == "outcome_reasons":
        body[field] = ["FAKE_PASS"]
    elif field == "review_requirements":
        body[field][0]["satisfied"] = True
    else:
        body[field] = [
            {
                "event_id": "fake",
                "event_type": "status.transitioned",
                "occurred_at": body["created_at"],
                "actor": {"id": "fake", "role": "VALIDATOR", "kind": "HUMAN"},
                "from_status": "DRAFT",
                "to_status": "VALIDATION",
                "reason_codes": [],
                "payload_hash": "sha256:" + "0" * 64,
                "previous_event_hash": None,
            }
        ]
    assert client.post("/v1/decisions", json=body, headers=headers("gen")).status_code == 422
    assert repository.get_decision(TENANT, body["decision_id"]) is None


@pytest.mark.parametrize(
    "token,expected",
    [
        ("gen", 403),
        ("val", 403),
        ("agent", 403),
        ("service", 403),
        ("admin", 403),
        ("self", 409),
        ("requester", 409),
        ("validator-app", 409),
        ("other", 404),
    ],
)
def test_only_independent_human_approver_can_transition(boundary, token, expected):  # type: ignore[no-untyped-def]
    client, repository = boundary
    review = to_review(client)
    response = client.post(
        f"/v1/decisions/{review['decision_id']}/transitions",
        json={"target": "APPROVED"},
        headers=headers(token, "approve"),
    )
    assert response.status_code == expected
    assert repository.get_decision(TENANT, review["decision_id"]) == review


@pytest.mark.parametrize("locale", ["de", "en"])
def test_human_approval_snapshot_replay_and_terminal_immutability(boundary, locale):  # type: ignore[no-untyped-def]
    client, repository = boundary
    review = to_review(client)
    path = f"/v1/decisions/{review['decision_id']}"
    response = client.post(
        path + "/transitions",
        json={"target": "APPROVED"},
        headers=headers("app", "approve", locale),
    )
    assert response.status_code == 200
    approved = response.json()
    assert approved["approvals"][0]["approver"] == {
        "id": "approver",
        "role": "APPROVER",
        "kind": "HUMAN",
    }
    event = approved["audit_events"][-1]
    assert event["tenant_id"] == TENANT.tenant_id
    assert event["payload_hash"] == payload_hash(
        {
            "tenant_id": TENANT.tenant_id,
            "after_document_hash": payload_hash(
                {**approved, "audit_events": approved["audit_events"][:-1]}
            ),
            "from": "REVIEW",
            "to": "APPROVED",
            "actor": event["actor"],
        }
    )
    replay = client.post(
        path + "/transitions",
        json={"target": "APPROVED"},
        headers=headers("app", "approve", locale),
    )
    assert replay.status_code == 200 and replay.json() == approved
    assert (
        client.post(
            path + "/transitions", json={"target": "APPROVED"}, headers=headers("app", "fresh")
        ).status_code
        == 409
    )
    assert (
        client.post(path + "/evaluate", headers=headers("val", "terminal-eval")).status_code == 409
    )
    assert repository.get_decision(TENANT, review["decision_id"]) == approved
    # Reimporting an approval under another id/tenant cannot confer authority.
    approved["decision_id"] = "REPLAY-COPY"
    assert (
        client.post("/v1/decisions", json=approved, headers=headers("gen", "copy")).status_code
        == 422
    )


def test_tenant_override_is_rejected_before_approval(boundary):  # type: ignore[no-untyped-def]
    client, repository = boundary
    review = to_review(client)
    auth = {**headers("app", "tenant-switch"), "X-Tenant-ID": "tenant-b"}
    assert (
        client.post(
            f"/v1/decisions/{review['decision_id']}/transitions",
            json={"target": "APPROVED"},
            headers=auth,
        ).status_code
        == 403
    )
    assert repository.get_decision(TENANT, review["decision_id"]) == review


def test_concurrent_approvals_commit_once(boundary, monkeypatch):  # type: ignore[no-untyped-def]
    client, repository = boundary
    review = to_review(client)
    barrier = Barrier(2)
    original_save = repository.save_result

    def competing_save(*args, **kwargs):  # type: ignore[no-untyped-def]
        barrier.wait(timeout=10)
        return original_save(*args, **kwargs)

    monkeypatch.setattr(repository, "save_result", competing_save)

    def approve(key):  # type: ignore[no-untyped-def]
        return client.post(
            f"/v1/decisions/{review['decision_id']}/transitions",
            json={"target": "APPROVED"},
            headers=headers("app", key),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(approve, ["race-1", "race-2"]))
    assert sorted(result.status_code for result in results) == [200, 409]
    stored = repository.get_decision(TENANT, review["decision_id"])
    assert len(stored["approvals"]) == 1
    assert len(stored["audit_events"]) == len(review["audit_events"]) + 1
    winner = next(result.json() for result in results if result.status_code == 200)
    assert stored == winner


def test_evaluation_racing_approval_cannot_overwrite_it(boundary, monkeypatch):  # type: ignore[no-untyped-def]
    client, repository = boundary
    review = to_review(client)
    path = f"/v1/decisions/{review['decision_id']}"
    original_save = repository.save_result
    winner = None

    def save_with_interleaved_approval(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal winner
        if args[2] is not None:
            winner = client.post(
                path + "/transitions",
                json={"target": "APPROVED"},
                headers=headers("app", "approve-race"),
            )
            assert winner.status_code == 200
        return original_save(*args, **kwargs)

    monkeypatch.setattr(repository, "save_result", save_with_interleaved_approval)
    response = client.post(path + "/evaluate", headers=headers("val", "evaluate-race"))
    assert response.status_code == 409
    assert winner is not None
    assert repository.get_decision(TENANT, review["decision_id"]) == winner.json()


@pytest.mark.parametrize("material_field", ["claims", "policies", "evidence", "constraints"])
def test_changed_decision_snapshot_cannot_be_approved(boundary, monkeypatch, material_field):  # type: ignore[no-untyped-def]
    client, repository = boundary
    review = to_review(client)
    changed = copy.deepcopy(review)
    if material_field == "claims":
        changed["claims"][0]["statement"] = "Changed claim"
    elif material_field == "policies":
        changed["policies"][0]["version"] = "2.0"
    elif material_field == "evidence":
        changed["evidence"][0]["content_hash"] = "sha256:changed"
    else:
        changed["constraints"][0]["satisfied"] = False
    original_save = repository.save_result

    def change_before_commit(*args, **kwargs):  # type: ignore[no-untyped-def]
        # Simulate a trusted concurrent writer after the API authorized its snapshot.
        original_save(TENANT, changed, None, [], expected_document=review)
        return original_save(*args, **kwargs)

    monkeypatch.setattr(repository, "save_result", change_before_commit)
    response = client.post(
        f"/v1/decisions/{review['decision_id']}/transitions",
        json={"target": "APPROVED"},
        headers=headers("app", "stale-approve"),
    )
    assert response.status_code == 409
    assert repository.get_decision(TENANT, review["decision_id"]) == changed
    assert (
        repository.get_idempotency(
            TENANT,
            "approver",
            f"decision:transition:{review['decision_id']}:APPROVED",
            "stale-approve",
            payload_hash({"target": "APPROVED"}),
        )
        is None
    )
    assert (
        repository.list_audit(TENANT, review["decision_id"], limit=100, offset=0)
        == review["audit_events"]
    )


def test_create_replay_never_imports_authority(boundary):  # type: ignore[no-untyped-def]
    client, repository = boundary
    body = document()
    first = client.post("/v1/decisions", json=body, headers=headers("gen"))
    assert first.status_code == 201
    assert client.post("/v1/decisions", json=body, headers=headers("gen")).json() == first.json()
    body["status"] = "APPROVED"
    assert client.post("/v1/decisions", json=body, headers=headers("gen")).status_code == 422
    assert repository.get_decision(TENANT, body["decision_id"]) == first.json()


def test_transition_body_cannot_supply_actor_or_approval(boundary):  # type: ignore[no-untyped-def]
    client, repository = boundary
    review = to_review(client)
    response = client.post(
        f"/v1/decisions/{review['decision_id']}/transitions",
        json={"target": "APPROVED", "actor": {"id": "approver", "kind": "HUMAN"}, "approvals": []},
        headers=headers("gen"),
    )
    assert response.status_code == 422
    assert repository.get_decision(TENANT, review["decision_id"]) == review
