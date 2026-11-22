"""Authenticated B2 API boundary with synthetic independent verifier records."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from decision_assurance.api.app import create_app
from decision_assurance.decision_file import load_decision_file
from decision_assurance.identity import ActorKind, Identity, Role, StaticTokenAuthenticator
from decision_assurance.provenance.evidence import (
    EvidenceVerification,
    InMemoryEvidenceRegistry,
    evidence_binding,
)
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.tenancy import TenantContext

ROOT = Path(__file__).parents[2]
CODE = "EVIDENCE_PROVENANCE_UNVERIFIED"


def document() -> dict[str, Any]:
    doc = load_decision_file(ROOT / "examples/decision-cases/low-risk-pass.json")
    doc["created_by"] = {"id": "generator-a", "role": "GENERATOR", "kind": "AGENT"}
    doc["evidence"][0]["source_ref"] = "independent-archive/source-1"
    doc["evidence"][0]["content_hash"] = "sha256:" + "a" * 64
    return doc


def verification(doc: dict[str, Any]) -> EvidenceVerification:
    now = datetime.now(timezone.utc)
    return EvidenceVerification(
        verification_id="independent-verification-1",
        tenant_id="tenant-a",
        decision_id=doc["decision_id"],
        evidence_id=doc["evidence"][0]["id"],
        generator_id="generator-a",
        validator_id="independent-verifier",
        binding_hash=evidence_binding(
            {
                "decision_id": doc["decision_id"],
                "claims": doc["claims"],
                "policies": doc["policies"],
                "policy_version": ",".join(p["version"] for p in doc["policies"]) or "none",
            },
            doc["evidence"][0],
        ),
        verified_at=now - timedelta(minutes=1),
        valid_until=now + timedelta(minutes=5),
    )


def harness(tmp_path: Path, records: tuple[EvidenceVerification, ...] = ()) -> TestClient:
    repository = SqliteDecisionRepository(tmp_path / "b2.sqlite")
    repository.initialize()
    identities = {
        f"{tenant}-{role}": Identity(
            f"{role}-a",
            TenantContext(f"tenant-{tenant}"),
            Role.GENERATOR if role == "generator" else Role.VALIDATOR,
            ActorKind.AGENT if role == "generator" else ActorKind.HUMAN,
        )
        for tenant in ("a", "b")
        for role in ("generator", "validator")
    }
    return TestClient(
        create_app(
            repository,
            StaticTokenAuthenticator(identities),
            evidence_registry=InMemoryEvidenceRegistry(records),
        )
    )


def headers(token: str, key: str, locale: str = "en") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key, "Accept-Language": locale}


@pytest.mark.parametrize("locale", ["de", "en"])
@pytest.mark.parametrize(
    "attack",
    [
        "spoofed-source",
        "changed-hash",
        "changed-claim",
        "wrong-tenant",
        "missing-registry",
        "positive",
    ],
)
def test_authenticated_evidence_boundary(tmp_path: Path, locale: str, attack: str) -> None:
    doc = document()
    trusted = verification(doc)
    client = harness(tmp_path, () if attack == "missing-registry" else (trusted,))
    tenant = "b" if attack == "wrong-tenant" else "a"
    if attack == "spoofed-source":
        doc["evidence"][0]["source_ref"] = "untrusted/attacker-email.txt"
    elif attack == "changed-hash":
        doc["evidence"][0]["content_hash"] = "sha256:" + "b" * 64
    elif attack == "changed-claim":
        doc["claims"][0]["statement"] = "Manipulated claim"
    assert (
        client.post(
            "/v1/decisions", headers=headers(f"{tenant}-generator", "create", locale), json=doc
        ).status_code
        == 201
    )
    route = f"/v1/decisions/{doc['decision_id']}"
    # A generator cannot become the evaluator via source metadata or a role assertion.
    assert (
        client.post(
            route + "/evaluate", headers=headers(f"{tenant}-generator", "denied", locale)
        ).status_code
        == 403
    )
    response = client.post(
        route + "/evaluate", headers=headers(f"{tenant}-validator", "evaluate", locale)
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == ("PASS" if attack == "positive" else "REVIEW")
    if attack != "positive":
        assert CODE in response.json()["reason_codes"]
    stored = client.get(route, headers=headers(f"{tenant}-validator", "read", locale)).json()
    assert stored["status"] == "DRAFT"
    assert stored["evidence"] == doc["evidence"]  # supplied assertion preserved, never authority
    event = stored["audit_events"][-1]
    assert event["from_status"] == event["to_status"] == "DRAFT"
    assert event["tenant_id"] == f"tenant-{tenant}"
    assert event["correlation_id"]
    other = "a" if tenant == "b" else "b"
    assert (
        client.post(
            route + "/evaluate", headers=headers(f"{other}-validator", "cross", locale)
        ).status_code
        == 404
    )


def test_embedded_proof_and_tenant_authority_are_rejected_by_contract(tmp_path: Path) -> None:
    client = harness(tmp_path)
    for injection in ({"verification": {"status": "VERIFIED"}}, {"tenant_id": "tenant-a"}):
        doc = copy.deepcopy(document())
        doc["evidence"][0].update(injection)
        assert (
            client.post(
                "/v1/decisions", headers=headers("a-generator", str(injection)), json=doc
            ).status_code
            == 422
        )
