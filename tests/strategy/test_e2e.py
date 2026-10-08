import copy
import json

import pytest
from fastapi.testclient import TestClient

from decision_assurance.api.app import create_app
from decision_assurance.identity import ActorKind, Identity, Role, StaticTokenAuthenticator
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.strategy.store import SqliteStrategyStore
from decision_assurance.tenancy import TenantContext

from .test_adapter import ROOT, artifact, envelope


@pytest.mark.parametrize("locale", ["de", "en"])
def test_two_tenant_import_validate_and_observe(tmp_path, locale):
    repo = SqliteDecisionRepository(tmp_path / "e2e.db")
    repo.initialize()
    store = SqliteStrategyStore(tmp_path / "e2e.db")
    store.initialize()
    identities = {
        "gen": Identity("generator", TenantContext("tenant-a"), Role.GENERATOR, ActorKind.AGENT),
        "val": Identity("validator", TenantContext("tenant-a"), Role.VALIDATOR, ActorKind.HUMAN),
        "read": Identity("readonly", TenantContext("tenant-a"), Role.READONLY, ActorKind.HUMAN),
        "b": Identity("generator-b", TenantContext("tenant-b"), Role.GENERATOR, ActorKind.AGENT),
    }
    client = TestClient(
        create_app(repo, StaticTokenAuthenticator(identities), strategy_store=store)
    )

    def auth(identity_key="gen", key=None):
        result = {"Authorization": "Bearer " + identity_key, "Accept-Language": locale}
        if key:
            result["Idempotency-Key"] = key
        return result

    document = json.loads(
        (ROOT / "examples/decision-cases/low-risk-pass.json").read_text(encoding="utf-8")
    )
    document["decision_id"] = "DECISION-ORIGINAL"
    document["created_by"] = {"id": "generator", "role": "GENERATOR", "kind": "AGENT"}
    created = client.post("/v1/decisions", headers=auth(key="create"), json=document)
    assert created.status_code == 201
    document = created.json()
    data = envelope(document).model_dump()
    assert client.post("/v1/strategy/preview", headers=auth("read"), json=data).status_code == 200
    assert client.post("/v1/strategy/imports", json=data).status_code == 401
    assert client.post("/v1/strategy/imports", headers=auth("read"), json=data).status_code == 403
    assert client.post("/v1/strategy/imports", headers=auth("b"), json=data).status_code == 403
    before = client.get("/v1/decisions/DECISION-ORIGINAL", headers=auth()).json()
    assert before == document
    imported = client.post("/v1/strategy/imports", headers=auth(), json=data)
    assert imported.status_code == 200
    assert client.post("/v1/strategy/imports", headers=auth(), json=data).json() == imported.json()
    assert (
        client.get("/v1/strategy/artifacts/" + artifact()["id"], headers=auth("b")).status_code
        == 404
    )
    evaluated = client.post("/v1/decisions/DECISION-ORIGINAL/evaluate", headers=auth("val", "eval"))
    assert evaluated.status_code == 200 and evaluated.json()["outcome"] == "BLOCK"
    terminal = client.post(
        "/v1/decisions/DECISION-ORIGINAL/transitions",
        headers=auth("val", "block"),
        json={"target": "BLOCKED"},
    )
    assert terminal.status_code == 200
    historical = terminal.json()
    observation = envelope(historical, mode="observation", selected_option_id=None).model_dump()
    observation["artifact"]["id"] = "STR-OBSERVATION-1"
    observed = client.post("/v1/strategy/imports", headers=auth(), json=observation)
    assert observed.status_code == 200 and observed.json()["new_case_proposal"] is True
    assert client.get("/v1/decisions/DECISION-ORIGINAL", headers=auth()).json() == historical
    stored = client.get("/v1/strategy/artifacts/STR-OBSERVATION-1", headers=auth()).json()
    assert stored["original"]["results"]["attribution"] == "unresolved"
    assert stored["original"]["baseline"]["metrics"][0]["expected"]["value"] == 70
    assert stored["original"]["request"]["value"]["actuals"]["M-WORKLOAD"]["value"] == 55
    assert store.get(identities["gen"], "B-ORIGINAL")["binding"]["status"] == "DRAFT"
    prohibited = envelope(historical).model_dump()
    prohibited["artifact"]["id"] = "STR-TERMINAL-MUTATION"
    assert client.post("/v1/strategy/imports", headers=auth(), json=prohibited).status_code == 409
    invalid = copy.deepcopy(observation)
    invalid["artifact"]["id"] = "STR-INJECTED"
    invalid["artifact"]["approvals"] = [{"role": "APPROVER"}]
    assert client.post("/v1/strategy/imports", headers=auth(), json=invalid).status_code == 422
    assert client.get("/v1/decisions/DECISION-ORIGINAL", headers=auth()).json() == historical
    b_document = copy.deepcopy(document)
    b_document["created_by"] = {"id": "generator-b", "role": "GENERATOR", "kind": "AGENT"}
    b_document["audit_events"] = []
    b_created = client.post("/v1/decisions", headers=auth("b", "b-create"), json=b_document)
    assert b_created.status_code == 201
    b_request = envelope(
        b_created.json(), tenant_id="tenant-b", selected_option_id="O-SCALE"
    ).model_dump()
    assert client.post("/v1/strategy/imports", headers=auth("b"), json=b_request).status_code == 200
    b_record = client.get("/v1/strategy/artifacts/" + artifact()["id"], headers=auth("b")).json()
    assert b_record["tenant_id"] == "tenant-b"
    assert store.get(identities["gen"], artifact()["id"])["tenant_id"] == "tenant-a"
    assert client.get("/v1/decisions/DECISION-ORIGINAL", headers=auth()).json() == historical


def test_locale_fallback_and_expired_session(tmp_path):
    class Expired:
        def authenticate(self, token):
            class Error(ValueError):
                reason_code = "AUTH_TOKEN_EXPIRED"

            raise Error()

    repo = SqliteDecisionRepository(tmp_path / "expiry.db")
    repo.initialize()
    client = TestClient(
        create_app(repo, Expired(), strategy_store=SqliteStrategyStore(tmp_path / "expiry.db"))
    )
    body = envelope({"decision_id": "DECISION-ORIGINAL"}).model_dump()
    for locale, message in [
        ("de", "Authentifizierung erforderlich."),
        ("en", "Authentication required."),
        ("fr", "Authentication required."),
    ]:
        response = client.post(
            "/v1/strategy/preview",
            json=body,
            headers={"Authorization": "Bearer expired", "Accept-Language": locale},
        )
        assert response.status_code == 401
        assert response.json()["message"] == message
        assert response.json()["details"]["reason_code"] == "AUTH_TOKEN_EXPIRED"


def test_cli_preview_is_read_only(tmp_path):
    from decision_assurance.cli import main

    document = json.loads(
        (ROOT / "examples/decision-cases/low-risk-pass.json").read_text(encoding="utf-8")
    )
    document["decision_id"] = "DECISION-ORIGINAL"
    case = tmp_path / "case.json"
    request = tmp_path / "envelope.json"
    case.write_text(json.dumps(document), encoding="utf-8")
    request.write_text(envelope(document).model_dump_json(), encoding="utf-8")
    previous = case.read_bytes(), request.read_bytes()
    assert main(["strategy-preview", str(case), str(request), "--locale", "de"]) == 0
    assert (case.read_bytes(), request.read_bytes()) == previous
