from __future__ import annotations

import hashlib
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
    InMemoryAcceptanceAudit,
    InMemoryEvidenceArtifactResolver,
    PilotAcceptanceGate,
    PilotAcceptanceTransition,
    TlsEvidence,
    load_deployment_bundle,
)
from decision_assurance.identity import ActorKind, Identity, Role
from decision_assurance.observability.alerts import AlertEvaluator, default_alert_rules
from decision_assurance.observability.metrics import InMemoryMetrics, initialize_pilot_metrics
from decision_assurance.recovery.evidence import RecoveryEvidence
from decision_assurance.tenancy import TenantContext

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
    items = []
    for kind in sorted(REQUIRED):
        artifact = _artifact_bytes(kind, verified, NOW, "MEASURED", "tenant-a")
        items.append(
            EvidenceItem(
                kind,
                verified,
                NOW,
                "sha256:" + hashlib.sha256(artifact).hexdigest(),
                "MEASURED",
                "pilot-eu-1",
                "tenant-a",
                "a" * 40,
            )
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
        evidence=tuple(items),
        provider_residency_status="ACCESS_BLOCKED",
        open_risks=("real public deployment evidence is pending",),
        creator=creator,
        created_at=NOW,
    )


def _artifact_bytes(
    kind: str, verified: bool, observed_at: datetime, source: str, tenant_id: str
) -> bytes:
    return json.dumps(
        {
            "kind": kind,
            "deployment_id": "pilot-eu-1",
            "tenant_id": tenant_id,
            "commit_sha": "a" * 40,
            "verified": verified,
            "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
            "source": source,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _artifact_for(item: EvidenceItem) -> bytes:
    return _artifact_bytes(item.kind, item.verified, item.observed_at, item.source, item.tenant_id)


def _gate(bundle: DeploymentBundle, max_age: timedelta) -> PilotAcceptanceGate:
    return PilotAcceptanceGate(
        max_age=max_age,
        evidence_resolver=InMemoryEvidenceArtifactResolver(
            {item.digest: _artifact_for(item) for item in bundle.evidence}
        ),
    )


def test_technical_gate_never_auto_accepts_and_human_transition_is_independent() -> None:
    bundle = _bundle()
    result = _gate(bundle, timedelta(days=7)).evaluate(bundle, now=NOW)
    assert result.status is EvidenceStatus.PILOT_REVIEW_REQUIRED
    assert result.reasons == ()

    audit = InMemoryAcceptanceAudit()
    transition = PilotAcceptanceTransition(audit, clock=lambda: NOW)
    creator = Identity("operator-a", TenantContext("tenant-a"), Role.REVIEWER, ActorKind.HUMAN)
    reviewer = Identity("reviewer-b", TenantContext("tenant-a"), Role.REVIEWER, ActorKind.HUMAN)
    with pytest.raises(ValueError, match="ACCEPTANCE_ACTOR_INDEPENDENCE_REQUIRED"):
        transition.accept(bundle, result, reviewer=creator, correlation_id="accept-1")
    accepted = transition.accept(bundle, result, reviewer=reviewer, correlation_id="accept-2")
    assert accepted.status is EvidenceStatus.PILOT_ACCEPTED
    assert accepted.reviewer == "reviewer-b"
    assert len(audit.events) == 1
    assert audit.events[0].event_type == "deployment.pilot-accepted"
    assert accepted.audit_event_id == audit.events[0].event_id
    with pytest.raises(ValueError, match="ACCEPTANCE_RECORD_REQUIRED"):
        _bundle().as_dict(EvidenceStatus.PILOT_ACCEPTED)
    with pytest.raises(ValueError, match="TECHNICAL_EVIDENCE_GATE_REQUIRED"):
        transition.accept(
            _bundle(),
            _gate(bundle, timedelta(seconds=0)).evaluate(bundle, now=NOW + timedelta(seconds=1)),
            reviewer=reviewer,
            correlation_id="accept-3",
        )

    for invalid in (
        Identity("service-agent", TenantContext("tenant-a"), Role.REVIEWER, ActorKind.SERVICE),
        Identity("reviewer-c", TenantContext("tenant-b"), Role.REVIEWER, ActorKind.HUMAN),
        Identity("auditor", TenantContext("tenant-a"), Role.AUDITOR, ActorKind.HUMAN),
    ):
        with pytest.raises(ValueError):
            transition.accept(bundle, result, reviewer=invalid, correlation_id="accept-invalid")


def test_gate_blocks_missing_tampered_stale_or_self_declared_evidence() -> None:
    incomplete = _bundle(verified=False)
    assert (
        _gate(incomplete, timedelta(hours=24)).evaluate(incomplete, now=NOW).status
        is EvidenceStatus.BLOCKED
    )

    with pytest.raises(ValueError, match="INVALID_EVIDENCE_DIGEST"):
        EvidenceItem(
            "ALERT_TEST_EVIDENCE",
            True,
            NOW,
            "not-a-digest",
            "MEASURED",
            "pilot-eu-1",
            "tenant-a",
            "a" * 40,
        )

    stale = _bundle().with_created_at(NOW - timedelta(days=2))
    assert (
        _gate(stale, timedelta(hours=24)).evaluate(stale, now=NOW).status is EvidenceStatus.BLOCKED
    )
    stale_items = tuple(
        EvidenceItem(
            item.kind,
            True,
            NOW - timedelta(days=3650),
            item.digest,
            item.source,
            item.deployment_id,
            item.tenant_id,
            item.commit_sha,
        )
        for item in _bundle().evidence
    )
    stale_bundle = _bundle().with_evidence(stale_items)
    stale_result = _gate(stale_bundle, timedelta(hours=24)).evaluate(stale_bundle, now=NOW)
    assert stale_result.status is EvidenceStatus.BLOCKED
    assert "STALE_REQUIRED_EVIDENCE" in stale_result.reasons
    declared = list(_bundle().evidence)
    declared[0] = EvidenceItem(
        declared[0].kind,
        True,
        NOW,
        declared[0].digest,
        "SELF_DECLARED",
        declared[0].deployment_id,
        declared[0].tenant_id,
        declared[0].commit_sha,
    )
    assert (
        _gate(_bundle().with_evidence(tuple(declared)), timedelta(hours=24))
        .evaluate(_bundle().with_evidence(tuple(declared)), now=NOW)
        .status
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
    partial_wildcard = TlsEvidence(
        "researchfoo.example",
        ("research*.example",),
        valid.not_before,
        valid.not_after,
        True,
        "1.3",
        "MEASURED",
    )
    with pytest.raises(ValueError, match="TLS_CERTIFICATE_HOST_MISMATCH"):
        partial_wildcard.verify("researchfoo.example", NOW)


def test_gate_rejects_cross_tenant_or_commit_evidence_replay() -> None:
    original = _bundle()
    replayed = original.with_evidence(
        tuple(
            EvidenceItem(
                item.kind,
                item.verified,
                item.observed_at,
                item.digest,
                item.source,
                item.deployment_id,
                "tenant-b",
                item.commit_sha,
            )
            for item in original.evidence
        )
    )
    result = PilotAcceptanceGate(
        max_age=timedelta(days=1),
        evidence_resolver=InMemoryEvidenceArtifactResolver(
            {item.digest: _artifact_for(item) for item in original.evidence}
        ),
    ).evaluate(replayed, now=NOW)
    assert result.status is EvidenceStatus.BLOCKED
    assert "EVIDENCE_BINDING_MISMATCH" in result.reasons
    assert "EVIDENCE_ARTIFACT_UNRESOLVED" in result.reasons


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
        session_decryption_valid=True,
        verification_report_sha256="sha256:" + "f" * 64,
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
    metrics = InMemoryMetrics()
    metrics.increment("export_signature_failures_total")
    metrics.set_gauge("session_store_available", 1)
    rendered = metrics.render_prometheus()
    assert "export_signature_failures_total 1" in rendered
    assert "session_store_available 1" in rendered
    firing = AlertEvaluator(rules).evaluate(
        {"export_signature_failures_total": 1.0, "session_store_available": 1.0}
    )
    assert "ExportSignatureFailure" in firing
    missing = AlertEvaluator(rules).evaluate({})
    assert "SessionStoreUnavailable" in missing
    assert "BackupFailure" in missing
    assert "RestoreFailure" in missing
    assert "CertificateExpiring" in missing
    assert "KeycloakUnavailable" in missing

    baseline = InMemoryMetrics()
    initialize_pilot_metrics(baseline)
    baseline_rendered = baseline.render_prometheus()
    assert "backup_success 0" in baseline_rendered
    assert "restore_success 0" in baseline_rendered
    assert "keycloak_available 0" in baseline_rendered


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
    assert "absent(session_store_available)" in raw
    assert "absent(restore_success)" in raw
    assert "absent(keycloak_available)" in raw


def test_deployment_bundle_round_trip_rejects_secret_fields() -> None:
    payload = _bundle().as_dict(EvidenceStatus.PILOT_REVIEW_REQUIRED)
    loaded = load_deployment_bundle(json.dumps(payload).encode())
    assert loaded.deployment_id == "pilot-eu-1"
    with pytest.raises(ValueError, match="INVALID_DEPLOYMENT_BUNDLE"):
        load_deployment_bundle(json.dumps({**payload, "private_key": "canary"}).encode())
