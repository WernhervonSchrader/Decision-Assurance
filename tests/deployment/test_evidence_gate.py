from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from decision_assurance.deployment.evidence import (
    DeploymentBundle,
    EvidenceItem,
    EvidenceStatus,
    PilotAcceptanceGate,
    PilotAcceptanceTransition,
    TlsEvidence,
    load_deployment_bundle,
)
from decision_assurance.observability.alerts import AlertEvaluator, default_alert_rules
from decision_assurance.recovery.evidence import RecoveryEvidence

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).parents[2]
REQUIRED = {
    "TLS_CERTIFICATE_EVIDENCE",
    "PUBLIC_HOST_EVIDENCE",
    "EDGE_CONFIGURATION_EVIDENCE",
    "OIDC_REDIRECT_EVIDENCE",
    "MFA_POLICY_EVIDENCE",
    "DATABASE_MIGRATION_EVIDENCE",
    "RECOVERY_EVIDENCE",
    "MONITORING_EVIDENCE",
    "ALERT_TEST_EVIDENCE",
    "MULTI_INSTANCE_EVIDENCE",
    "SIGNED_EXPORT_EVIDENCE",
    "RETENTION_LEGAL_HOLD_EVIDENCE",
    "INDEPENDENT_REVIEW_EVIDENCE",
}


def _bundle(*, verified: bool = True, creator: str = "operator-a") -> DeploymentBundle:
    items = tuple(
        EvidenceItem(kind, verified, NOW, "sha256:" + f"{index:064x}", "MEASURED")
        for index, kind in enumerate(sorted(REQUIRED), 1)
    )
    return DeploymentBundle(
        schema_version="1.0.0",
        deployment_id="pilot-eu-1",
        tenant_id="tenant-a",
        profile="controlled-pilot",
        commit_sha="a" * 40,
        image_digests={"api": "sha256:" + "b" * 64, "pilot-ui": "sha256:" + "c" * 64},
        sbom_checksums={"api": "sha256:" + "d" * 64},
        config_checksums={"pilot": "sha256:" + "e" * 64},
        evidence=items,
        provider_residency_status="BLOCKED",
        open_risks=("real public deployment evidence is pending",),
        creator=creator,
        created_at=NOW,
    )


def test_technical_gate_never_auto_accepts_and_human_transition_is_independent() -> None:
    result = PilotAcceptanceGate(max_age=timedelta(days=7)).evaluate(_bundle(), now=NOW)
    assert result.status is EvidenceStatus.PILOT_REVIEW_REQUIRED
    assert result.reasons == ()

    transition = PilotAcceptanceTransition()
    with pytest.raises(ValueError, match="ACCEPTANCE_ACTOR_INDEPENDENCE_REQUIRED"):
        transition.accept(
            _bundle(), result, reviewer="operator-a", reviewer_roles={"PILOT_REVIEWER"}
        )
    accepted = transition.accept(
        _bundle(), result, reviewer="reviewer-b", reviewer_roles={"PILOT_REVIEWER"}
    )
    assert accepted.status is EvidenceStatus.PILOT_ACCEPTED
    assert accepted.reviewer == "reviewer-b"
    with pytest.raises(ValueError, match="TECHNICAL_EVIDENCE_GATE_REQUIRED"):
        transition.accept(
            _bundle(),
            PilotAcceptanceGate(max_age=timedelta(seconds=0)).evaluate(
                _bundle(), now=NOW + timedelta(seconds=1)
            ),
            reviewer="reviewer-b",
            reviewer_roles={"PILOT_REVIEWER"},
        )


def test_gate_blocks_missing_tampered_stale_or_self_declared_evidence() -> None:
    gate = PilotAcceptanceGate(max_age=timedelta(hours=24))
    incomplete = _bundle(verified=False)
    assert gate.evaluate(incomplete, now=NOW).status is EvidenceStatus.BLOCKED

    with pytest.raises(ValueError, match="INVALID_EVIDENCE_DIGEST"):
        EvidenceItem("ALERT_TEST_EVIDENCE", True, NOW, "not-a-digest", "MEASURED")

    stale = _bundle().with_created_at(NOW - timedelta(days=2))
    assert gate.evaluate(stale, now=NOW).status is EvidenceStatus.BLOCKED
    declared = list(_bundle().evidence)
    declared[0] = EvidenceItem(declared[0].kind, True, NOW, declared[0].digest, "SELF_DECLARED")
    assert (
        gate.evaluate(_bundle().with_evidence(tuple(declared)), now=NOW).status
        is EvidenceStatus.BLOCKED
    )


def test_tls_evidence_checks_host_validity_chain_and_measurement() -> None:
    valid = TlsEvidence(
        host="research.pilot.example",
        certificate_hosts=("research.pilot.example",),
        not_before=NOW - timedelta(days=1),
        not_after=NOW + timedelta(days=30),
        chain_verified=True,
        minimum_tls="1.3",
        source="MEASURED",
    )
    valid.verify("research.pilot.example", NOW)
    for changed in (
        TlsEvidence(
            "research.pilot.example",
            ("other.example",),
            valid.not_before,
            valid.not_after,
            True,
            "1.3",
            "MEASURED",
        ),
        TlsEvidence(
            "research.pilot.example",
            valid.certificate_hosts,
            valid.not_before,
            NOW - timedelta(seconds=1),
            True,
            "1.3",
            "MEASURED",
        ),
        TlsEvidence(
            "research.pilot.example",
            valid.certificate_hosts,
            valid.not_before,
            valid.not_after,
            False,
            "1.3",
            "MEASURED",
        ),
        TlsEvidence(
            "research.pilot.example",
            valid.certificate_hosts,
            valid.not_before,
            valid.not_after,
            True,
            "1.2",
            "SELF_DECLARED",
        ),
    ):
        with pytest.raises(ValueError):
            changed.verify("research.pilot.example", NOW)


def test_recovery_evidence_reports_observed_not_promised_rpo_rto() -> None:
    evidence = RecoveryEvidence(
        schema_version="1.0.0",
        environment="isolated-postgresql-16",
        commit_sha="a" * 40,
        data_bytes=4096,
        backup_started=NOW,
        backup_completed=NOW + timedelta(seconds=4),
        failure_at=NOW + timedelta(seconds=10),
        restore_started=NOW + timedelta(seconds=12),
        restore_completed=NOW + timedelta(seconds=40),
        latest_restored_record_at=NOW + timedelta(seconds=4),
        audit_chains_valid=True,
        exports_valid=True,
        tenant_isolation_valid=True,
        target_rpo_seconds=60,
        target_rto_seconds=120,
    )
    report = evidence.report()
    assert report["observed_rpo_seconds"] == 6
    assert report["observed_rto_seconds"] == 30
    assert report["target_met"] is True
    assert report["scope"] == "TEST_OBSERVATION_NOT_SERVICE_COMMITMENT"


def test_local_alert_evaluator_fires_without_high_cardinality_labels() -> None:
    rules = default_alert_rules()
    assert all(
        not rule.labels.intersection({"tenant", "actor", "decision", "url", "claim"})
        for rule in rules
    )
    firing = AlertEvaluator(rules).evaluate(
        {"da_export_signature_failures_total": 2.0, "da_session_store_available": 1.0}
    )
    assert "ExportSignatureFailure" in firing


def test_evidence_schemas_are_packaged_and_alert_rules_are_bounded() -> None:
    for name in ("deployment-evidence", "recovery-evidence"):
        public = ROOT / "schemas" / "production" / f"{name}.schema.json"
        packaged = (
            ROOT / "src" / "decision_assurance" / "schemas" / "production" / f"{name}.schema.json"
        )
        assert public.read_bytes() == packaged.read_bytes()
        Draft202012Validator.check_schema(json.loads(public.read_text(encoding="utf-8")))
    groups = yaml.safe_load(
        (ROOT / "deploy" / "observability" / "decision-assurance-alerts.yml").read_text(
            encoding="utf-8"
        )
    )["groups"]
    raw = json.dumps(groups).casefold()
    assert all(name not in raw for name in ("tenant_id", "actor_id", "decision_id", "url", "claim"))
    assert any(rule["alert"] == "ExportSignatureFailure" for rule in groups[0]["rules"])


def test_deployment_bundle_round_trip_rejects_secret_fields() -> None:
    payload = _bundle().as_dict(EvidenceStatus.PILOT_REVIEW_REQUIRED)
    loaded = load_deployment_bundle(json.dumps(payload).encode())
    assert loaded.deployment_id == "pilot-eu-1"
    with pytest.raises(ValueError, match="INVALID_DEPLOYMENT_BUNDLE"):
        load_deployment_bundle(json.dumps({**payload, "private_key": "canary"}).encode())
