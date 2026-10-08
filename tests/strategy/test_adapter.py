import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from decision_assurance.audit import payload_hash
from decision_assurance.decision_file import evaluate_decision_file
from decision_assurance.identity import ActorKind, Identity, Role
from decision_assurance.repositories.sqlite import SqliteDecisionRepository
from decision_assurance.strategy.contracts import ImportEnvelope
from decision_assurance.strategy.store import SqliteStrategyStore
from decision_assurance.tenancy import TenantContext

ROOT = Path(__file__).parents[2]
FIXTURES = Path(__file__).parent / "fixtures"


def artifact():
    return json.loads((FIXTURES / "valid-artifact.json").read_text(encoding="utf-8"))


def envelope(document, **updates):
    data = dict(
        adapter_version="rif-3.4-rc3/da-1",
        tenant_id="tenant-a",
        decision_id=document["decision_id"],
        expected_document_hash=payload_hash(document),
        mode="draft",
        content_language="en",
        selected_option_id="O-PILOT",
        provenance=dict(
            producer="synthetic-rif",
            locator="local:fixture",
            source_commit=None,
            local_modifications=None,
            file_hashes={},
            test_reports=[],
        ),
        artifact=artifact(),
    )
    data.update(updates)
    return ImportEnvelope.model_validate(data)


@pytest.fixture
def setup(tmp_path):
    repo = SqliteDecisionRepository(tmp_path / "strategy.db")
    repo.initialize()
    store = SqliteStrategyStore(tmp_path / "strategy.db")
    store.initialize()
    document = json.loads(
        (ROOT / "examples/decision-cases/low-risk-pass.json").read_text(encoding="utf-8")
    )
    document["decision_id"] = "DECISION-ORIGINAL"
    document["audit_events"] = []
    repo.create_decision(TenantContext("tenant-a"), document)
    gen = Identity("generator", TenantContext("tenant-a"), Role.GENERATOR, ActorKind.AGENT)
    return repo, store, document, gen


def test_preview_import_and_independent_evaluation(setup):
    repo, store, document, gen = setup
    request = envelope(document)
    preview = store.preview(gen, request)
    assert repo.get_decision(gen.tenant, document["decision_id"]) == document
    assert store.get(gen, request.artifact["id"]) is None
    assert preview["complete_semantic_replay"] is False
    imported = store.import_artifact(gen, request, "corr-1")
    current = repo.get_decision(gen.tenant, document["decision_id"])
    for field in [
        "status",
        "decision_outcome",
        "approvals",
        "canonical_action",
        "validation_results",
    ]:
        assert current[field] == document[field]
    assert current["assumptions"][-1]["status"] == "UNVERIFIED"
    assert any(e["status"] == "CONFLICTING" for e in current["evidence"])
    assert all(
        e["status"] != "VERIFIED" for e in current["evidence"] if e["id"].startswith("strategy:")
    )
    assert store.import_artifact(gen, request, "corr-retry") == imported
    assert store.get(gen, request.artifact["id"])["original"] == request.artifact
    _, result = evaluate_decision_file(current)
    assert (
        result.outcome.value == "BLOCK"
    )  # imported hard compliance has no independent verification
    assert len(repo.list_audit(gen.tenant, document["decision_id"], limit=100, offset=0)) == 1


@pytest.mark.parametrize(
    "mutation", ["tenant", "case", "stale", "version", "reference", "status", "nan", "weights"]
)
def test_invalid_import_is_atomic(setup, mutation):
    repo, store, document, gen = setup
    data = envelope(document).model_dump()
    if mutation == "tenant":
        data["tenant_id"] = "tenant-b"
    elif mutation == "case":
        data["decision_id"] = "UNKNOWN"
    elif mutation == "stale":
        data["expected_document_hash"] = "sha256:" + "0" * 64
    elif mutation == "version":
        data["artifact"]["contract_version"] = "next"
    elif mutation == "reference":
        data["artifact"]["request"]["claims"][0]["source_ids"] = ["MISSING"]
    elif mutation == "status":
        data["artifact"]["decision_outcome"] = "PASS"
    elif mutation == "nan":
        data["artifact"]["request"]["options"]["criteria"][0]["minimum"] = float("nan")
    else:
        data["artifact"]["request"]["options"]["scenarios"][0]["weights"]["K-EASE"] = 0.4
    with pytest.raises((ValueError, PermissionError)):
        store.import_artifact(gen, ImportEnvelope.model_validate(data), "negative")
    assert repo.get_decision(gen.tenant, document["decision_id"]) == document
    assert repo.list_audit(gen.tenant, document["decision_id"], limit=100, offset=0) == []


def test_wrong_role_and_tenant_fail(setup):
    repo, store, document, gen = setup
    for identity in [
        Identity("read", gen.tenant, Role.READONLY, ActorKind.HUMAN),
        Identity("gen-b", TenantContext("tenant-b"), Role.GENERATOR, ActorKind.AGENT),
    ]:
        with pytest.raises((ValueError, PermissionError)):
            store.import_artifact(identity, envelope(document), "denied")
    store.import_artifact(gen, envelope(document), "ok")
    other = Identity("gen-b", TenantContext("tenant-b"), Role.GENERATOR, ActorKind.AGENT)
    assert store.get(other, artifact()["id"]) is None


def test_same_identity_concurrent_retries_converge(setup):
    repo, store, document, gen = setup
    request = envelope(document)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: store.import_artifact(gen, request, "parallel"), range(2))
        )
    assert results[0] == results[1]
    assert len(repo.list_audit(gen.tenant, document["decision_id"], limit=100, offset=0)) == 1


def test_forged_winner_rejected_and_violated_choice_blocks(setup):
    repo, store, document, gen = setup
    forged = envelope(document)
    forged.artifact["results"]["scenarios"][0]["winner"] = "O-SCALE"
    with pytest.raises(ValueError):
        store.preview(gen, forged)
    store.import_artifact(gen, envelope(document, selected_option_id="O-SCALE"), "violated")
    current = repo.get_decision(gen.tenant, document["decision_id"])
    assert any(
        c["reason_code"] == "STRATEGY_HARD_CONDITION_VIOLATED" for c in current["constraints"]
    )
    assert evaluate_decision_file(current)[1].outcome.value == "BLOCK"


@pytest.mark.parametrize(
    "name",
    [
        "invalid-authority.json",
        "invalid-reference.json",
        "invalid-weights.json",
        "invalid-forged-winner.json",
        "invalid-skill-metadata.json",
    ],
)
def test_real_rif_invalid_examples(setup, name):
    _, store, document, gen = setup
    invalid = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    with pytest.raises(ValueError):
        store.preview(gen, envelope(document, artifact=invalid))


@pytest.mark.parametrize(
    "report,expected",
    [
        (
            dict(
                method="cli",
                execution_status="COMPLETED",
                exit_code=0,
                checked_objects=2,
                checks=[
                    dict(
                        id="required",
                        required=True,
                        status="ERROR",
                        expected_rejection=False,
                        subject_ref="S-OBS",
                    )
                ],
            ),
            "TEST_INCOMPLETE",
        ),
        (
            dict(
                method="function",
                execution_status="COMPLETED",
                exit_code=0,
                checked_objects=0,
                checks=[],
            ),
            "TEST_EMPTY",
        ),
        (
            dict(
                method="static",
                execution_status="COMPLETED",
                exit_code=None,
                checked_objects=1,
                checks=[
                    dict(
                        id="negative",
                        required=True,
                        status="NOT_REPRODUCED",
                        expected_rejection=False,
                        subject_ref="S-OBS",
                    )
                ],
            ),
            "TEST_INCONCLUSIVE",
        ),
        (
            dict(
                method="cli",
                execution_status="COMPLETED",
                exit_code=0,
                checked_objects=1,
                checks=[
                    dict(
                        id="input-rejection",
                        required=True,
                        status="EXPECTED_REJECTION",
                        expected_rejection=True,
                        subject_ref="S-OBS",
                    )
                ],
            ),
            "TEST_REPORTED_COMPLETE_UNVERIFIED",
        ),
    ],
)
def test_v2_test_evidence_remains_unverified(setup, report, expected):
    _, store, document, gen = setup
    data = envelope(document).model_dump()
    report.update(
        id="REPORT-1",
        subject="fixture-check",
        source_ref="local:fixture",
        source_commit="named-commit",
        file_hashes={"fixture.json": "sha256:" + "a" * 64},
        local_modifications=True,
    )
    data["provenance"]["test_reports"] = [report]
    preview = store.preview(gen, ImportEnvelope.model_validate(data))
    assert expected in preview["reason_codes"]
    assert preview["test_reports"][0]["source_commit"] == "named-commit"
    assert preview["test_reports"][0]["local_modifications"] is True
    assert preview["test_reports"][0]["method"] == report["method"]
    assert preview["document"]["decision_outcome"] == document["decision_outcome"]
    assert preview["document"]["approvals"] == document["approvals"]


def test_baseline_immutable_observations_separate(setup):
    repo, store, document, gen = setup
    baseline = artifact()["baseline"]
    fixed = store.import_artifact(
        gen, envelope(document, mode="baseline", artifact=baseline, selected_option_id=None), "fix"
    )
    changed = copy.deepcopy(baseline)
    changed["expected_effect"] = "retroactive success"
    with pytest.raises(ValueError):
        store.import_artifact(
            gen,
            envelope(document, mode="baseline", artifact=changed, selected_option_id=None),
            "overwrite",
        )
    observation = envelope(document, mode="observation", selected_option_id=None)
    recorded = store.import_artifact(gen, observation, "observe")
    assert recorded["new_case_proposal"] is True
    assert repo.get_decision(gen.tenant, document["decision_id"]) == document
    assert store.get(gen, baseline["id"])["original"] == baseline
    assert fixed["binding"]["status"] == "DRAFT"
    assert store.get(gen, observation.artifact["id"])["baseline_ref"] == baseline["id"]
