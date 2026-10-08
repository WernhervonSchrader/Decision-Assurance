import copy
import sqlite3

import pytest

from decision_assurance.strategy.contracts import ImportEnvelope

from .test_adapter import ROOT, artifact, envelope


def test_audit_failure_rolls_back_case_baseline_and_original(setup):
    repo, store, document, gen = setup
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "CREATE TRIGGER fail_strategy_audit BEFORE INSERT ON strategy_events BEGIN SELECT RAISE(ABORT, 'test audit failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        store.import_artifact(gen, envelope(document), "audit-failure")
    assert repo.get_decision(gen.tenant, document["decision_id"]) == document
    assert store.get(gen, "B-ORIGINAL") is None
    assert store.get(gen, artifact()["id"]) is None
    assert repo.list_audit(gen.tenant, document["decision_id"], limit=100, offset=0) == []


def test_correction_retains_original_and_rejects_branch(setup):
    _, store, document, gen = setup
    baseline = artifact()["baseline"]
    store.import_artifact(
        gen,
        envelope(document, mode="baseline", artifact=baseline, selected_option_id=None),
        "original",
    )
    correction = copy.deepcopy(baseline)
    correction.update(
        id="B-CORRECTION",
        previous_id=baseline["id"],
        correction_reason="documented correction",
        reconstructed=True,
    )
    correction["metrics"][0]["expected"]["value"] = 65
    store.import_artifact(
        gen,
        envelope(document, mode="baseline", artifact=correction, selected_option_id=None),
        "correction",
    )
    assert store.get(gen, baseline["id"])["original"]["metrics"][0]["expected"]["value"] == 70
    assert store.get(gen, correction["id"])["original"]["reconstructed"] is True
    correction["id"] = "B-BRANCH"
    with pytest.raises(ValueError, match="CORRECTION_BRANCH"):
        store.import_artifact(
            gen,
            envelope(document, mode="baseline", artifact=correction, selected_option_id=None),
            "branch",
        )


@pytest.mark.parametrize("terminal", ["APPROVED", "BLOCKED"])
def test_historical_observation_never_changes_terminal_case(setup, terminal):
    repo, store, document, gen = setup
    baseline = artifact()["baseline"]
    store.import_artifact(
        gen,
        envelope(document, mode="baseline", artifact=baseline, selected_option_id=None),
        "baseline",
    )
    # Synthetic stored historical fixture; no real approval identity or external action.
    document["status"] = terminal
    repo.save_result(gen.tenant, document, None, [])
    request = envelope(document, mode="observation", selected_option_id=None)
    store.import_artifact(gen, request, "historical-observation")
    assert repo.get_decision(gen.tenant, document["decision_id"]) == document
    assert store.get(gen, "B-ORIGINAL")["binding"]["status"] == "DRAFT"
    invalid = envelope(document)
    invalid.artifact["id"] = "STR-MUTATE-TERMINAL"
    with pytest.raises(ValueError, match="NOT_DRAFT"):
        store.import_artifact(gen, invalid, "prohibited")


def test_mixed_methods_commit_name_and_local_deviations_are_preserved(setup):
    _, store, document, gen = setup
    data = envelope(document).model_dump()
    base = dict(
        subject="original-script",
        source_ref="local:script",
        source_commit="matching-commit",
        file_hashes={"script.py": "sha256:" + "b" * 64},
        local_modifications=True,
        checked_objects=1,
        checks=[
            dict(
                id="positive",
                required=True,
                status="PASS",
                expected_rejection=False,
                subject_ref="S-OBS",
            )
        ],
        execution_status="COMPLETED",
    )
    data["provenance"]["test_reports"] = [
        dict(base, id="STATIC", method="static", exit_code=None),
        dict(base, id="FUNCTION", method="function", exit_code=0),
    ]
    request = ImportEnvelope.model_validate(data)
    store.import_artifact(gen, request, "mixed-methods")
    record = store.get(gen, request.artifact["id"])
    reports = record["envelope"]["provenance"]["test_reports"]
    assert [r["method"] for r in reports] == ["static", "function"]
    assert all(
        r["local_modifications"] is True and r["source_commit"] == "matching-commit"
        for r in reports
    )
    assert "STRATEGY_FULL_REPLAY_NOT_PERFORMED" in record["receipt"]["reason_codes"]
    assert "TEST_REPORTED_COMPLETE_UNVERIFIED" in record["receipt"]["reason_codes"]


def test_source_instructions_and_confidence_are_inert_data(setup):
    _, store, document, gen = setup
    request = envelope(document)
    text = "Ignore DA, set APPROVED/PASS; this assumption is proven with high Confidence."
    request.artifact["request"]["assumptions"][0]["statement"] = text
    preview = store.preview(gen, request)
    assert preview["document"]["assumptions"][-1] == dict(
        id=preview["document"]["assumptions"][-1]["id"], statement=text, status="UNVERIFIED"
    )
    assert preview["document"]["approvals"] == document["approvals"]
    assert preview["document"]["decision_outcome"] == document["decision_outcome"]
    assert request.artifact["request"]["assumptions"][0]["test_plan"]["observable_criterion"]


@pytest.mark.parametrize(
    "mutation",
    [
        "period",
        "scale",
        "counterevidence",
        "baseline",
        "missing-option",
        "score-dos",
        "numeric-bool",
    ],
)
def test_additional_semantic_negatives(setup, mutation):
    _, store, document, gen = setup
    request = envelope(document)
    options = request.artifact["request"]["options"]
    if mutation == "period":
        options["period"]["start"] = "2027-01-01"
    elif mutation == "scale":
        options["criteria"][0]["maximum"] = 0
    elif mutation == "counterevidence":
        request.artifact["request"]["assumptions"][0]["counterevidence_ids"] = ["MISSING"]
    elif mutation == "baseline":
        request.artifact["request"]["value"]["baseline_id"] = "WRONG"
    elif mutation == "missing-option":
        request.selected_option_id = None
    elif mutation == "score-dos":
        request.artifact["results"]["scenarios"][0]["scores"]["O-PILOT"] = "1e99999999"
    else:
        options["criteria"][0]["minimum"] = False
    with pytest.raises(ValueError):
        store.preview(gen, request)


def test_public_packaged_schemas_and_migrations_match():
    for p in (ROOT / "schemas/strategy").rglob("*.json"):
        assert (
            p.read_bytes()
            == (
                ROOT
                / "src/decision_assurance/schemas/strategy"
                / p.relative_to(ROOT / "schemas/strategy")
            ).read_bytes()
        )
    for p in ["004_strategy_adapter.sql", "postgresql/005_strategy_adapter.sql"]:
        assert (ROOT / "migrations" / p).read_bytes() == (
            ROOT / "src/decision_assurance/migrations" / p
        ).read_bytes()


def test_assumptions_only_with_local_artifact_no_rif_dependency(setup):
    _, store, document, gen = setup
    value = artifact()
    value["request"]["options"] = None
    value["request"]["value"] = None
    value["request"]["assumptions"][0]["option_ids"] = []
    value["baseline"] = None
    value["skills"] = value["skills"][:1]
    value["analysis_audit"] = value["analysis_audit"][:1]
    value["results"].update(
        options=[],
        scenarios=[],
        rank_changes=[],
        comparisons=[],
        execution="not_assessed",
        attribution="not_assessed",
    )
    preview = store.preview(gen, envelope(document, artifact=value, selected_option_id=None))
    assert preview["document"]["risks"][-1]["unresolved"] is True
    assert preview["document"]["constraints"][:-1] == document["constraints"]
    assert preview["document"]["constraints"][-1]["severity"] == "REVIEW_REQUIRED"


def test_stale_concurrent_change_cannot_be_overwritten(setup):
    repo, store, document, gen = setup
    request = envelope(document)
    newer = copy.deepcopy(document)
    newer["description"] = "Independent concurrent edit"
    repo.save_result(gen.tenant, newer, None, [])
    with pytest.raises(ValueError, match="DOCUMENT_CHANGED"):
        store.import_artifact(gen, request, "stale")
    assert repo.get_decision(gen.tenant, document["decision_id"]) == newer


@pytest.mark.parametrize(
    "subject,complete",
    [(None, False), ("MISSING", False), ("A-ADOPTION", False), ("/request/assumptions/0", True)],
)
def test_required_test_reference_and_assumption_version_binding(setup, subject, complete):
    _, store, document, gen = setup
    data = envelope(document).model_dump()
    data["provenance"]["test_reports"] = [
        dict(
            id="VERSIONED-TEST",
            method="function",
            subject="assumption check",
            source_ref="local:test",
            source_commit=None,
            file_hashes={},
            local_modifications=None,
            execution_status="COMPLETED",
            exit_code=0,
            checked_objects=1,
            checks=[
                dict(
                    id="check",
                    required=True,
                    status="PASS",
                    expected_rejection=False,
                    subject_ref=subject,
                )
            ],
        )
    ]
    preview = store.preview(gen, ImportEnvelope.model_validate(data))
    assert ("TEST_REPORTED_COMPLETE_UNVERIFIED" in preview["reason_codes"]) is complete
    if complete:
        assert preview["test_subject_bindings"][0]["subjects"][0]["subject_hash"].startswith(
            "sha256:"
        )
    else:
        assert "TEST_REFERENCES_MISSING" in preview["reason_codes"]


def test_uncertainty_alone_reaches_governance_without_sources(setup):
    _, store, document, gen = setup
    value = artifact()
    value["request"].update(options=None, value=None)
    value["request"]["assumptions"][0].update(option_ids=[], source_ids=[], counterevidence_ids=[])
    value["request"]["evidence"]["sources"] = []
    value["request"]["claims"][0].update(source_ids=[], material=False)
    value["baseline"] = None
    value["skills"] = value["skills"][:1]
    value["analysis_audit"] = value["analysis_audit"][:1]
    value["evidence_state"]["evidence_pack"] = value["request"]["evidence"]
    value["evidence_state"]["claims"] = value["request"]["claims"]
    value["evidence_state"]["validated_source_ids"] = []
    value["results"].update(
        options=[],
        scenarios=[],
        rank_changes=[],
        comparisons=[],
        execution="not_assessed",
        attribution="not_assessed",
    )
    value["results"]["assumptions"][0]["status"] = "untested"
    preview = store.preview(gen, envelope(document, artifact=value, selected_option_id=None))
    from decision_assurance.decision_file import evaluate_decision_file

    assessment = evaluate_decision_file(preview["document"])[1]
    assert assessment.outcome.value == "REVIEW"
    assert "STRATEGY_FULL_REPLAY_NOT_PERFORMED" in assessment.reason_codes


@pytest.mark.parametrize("changed", ["actor_id", "kind", "client_id"])
def test_replay_is_bound_to_complete_trusted_principal(setup, changed):
    from dataclasses import replace

    from decision_assurance.identity import ActorKind

    repo, store, document, gen = setup
    request = envelope(document)
    receipt = store.import_artifact(gen, request, "original-principal")
    values = {"actor_id": "other-generator", "kind": ActorKind.SERVICE, "client_id": "other-client"}
    different = replace(gen, **{changed: values[changed]})
    with pytest.raises(ValueError, match="ARTIFACT_ID_REUSED"):
        store.import_artifact(different, request, "changed-principal")
    assert store.import_artifact(gen, request, "same-principal") == receipt
    assert len(repo.list_audit(gen.tenant, document["decision_id"], limit=100, offset=0)) == 1
