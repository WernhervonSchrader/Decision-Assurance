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
    FileEvidenceArtifactResolver,
    InMemoryAcceptanceAudit,
    InMemoryEvidenceArtifactResolver,
    PilotAcceptanceGate,
    PilotAcceptanceTransition,
    TlsEvidence,
    load_deployment_bundle,
)
from decision_assurance.identity import ActorKind, Identity, Role
from decision_assurance.observability.alerts import AlertEvaluator, default_alert_rules
from decision_assurance.observability.metrics import (
    AssuranceOutcomeCollector,
    InMemoryMetrics,
    PilotOperationalEvidenceCollector,
    initialize_pilot_metrics,
)
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
            "payload": _payload_for(kind),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _payload_for(kind: str) -> dict[str, object]:
    sha = "sha256:" + "f" * 64
    payloads: dict[str, dict[str, object]] = {
        "TLS_CERTIFICATE_EVIDENCE": {
            "host": "research.pilot.example",
            "certificate_sha256": sha,
            "not_before": (NOW - timedelta(days=1)).isoformat(),
            "not_after": (NOW + timedelta(days=30)).isoformat(),
            "chain_verified": True,
            "minimum_tls": "1.3",
        },
        "PUBLIC_HOST_EVIDENCE": {
            "hostname": "research.pilot.example",
            "resolved_addresses": ["1.1.1.1"],
            "public_only": True,
        },
        "EDGE_CONFIGURATION_EVIDENCE": {
            "config_sha256": sha,
            "host_allowlist_valid": True,
            "tls_redirect_valid": True,
            "validation_tool": "caddy-adapt",
        },
        "OIDC_REDIRECT_EVIDENCE": {
            "issuer": "https://identity.pilot.example/realms/da",
            "redirect_uri": "https://research.pilot.example/auth/callback",
            "exact_match": True,
            "pkce_required": True,
        },
        "MFA_POLICY_EVIDENCE": {
            "policy_version": "controlled-pilot-mfa-v1",
            "methods": ["otp", "webauthn"],
            "flow_tested": True,
        },
        "DATABASE_MIGRATION_EVIDENCE": {
            "database_schema_version": "004",
            "forced_rls_tables": 28,
            "application_role_tested": True,
            "migration_role_tested": True,
        },
        "RECOVERY_EVIDENCE": {
            "status": "PASS",
            "commit_sha": "a" * 40,
            "report_sha256": sha,
            "source_database": "decision_assurance",
            "restore_database": "da_restore",
            "observed_rpo_seconds": 5,
            "observed_rto_seconds": 20,
            "integrity_verified": True,
        },
        "MONITORING_EVIDENCE": {
            "scrape_endpoint": "https://research.pilot.example/internal/metrics",
            "metric_names": ["session_store_available", "keycloak_available"],
            "scrape_success": True,
        },
        "ALERT_TEST_EVIDENCE": {
            "alert_name": "SessionStoreUnavailable",
            "receiver": "pilot-ops",
            "triggered": True,
            "notification_received": True,
        },
        "MULTI_INSTANCE_EVIDENCE": {
            "instance_count": 2,
            "shared_session_verified": True,
            "cross_instance_revoke_verified": True,
            "tenant_isolation_verified": True,
        },
        "SIGNED_EXPORT_EVIDENCE": {
            "export_sha256": sha,
            "algorithm": "EdDSA",
            "key_id": "pilot-key-1",
            "offline_verified": True,
        },
        "RETENTION_LEGAL_HOLD_EVIDENCE": {
            "retention_policy_version": "pilot-retention-v1",
            "deletion_verified": True,
            "legal_hold_block_verified": True,
            "restore_resurrection_blocked": True,
        },
        "INDEPENDENT_REVIEW_EVIDENCE": {
            "reviewer_id": "independent-reviewer",
            "reviewed_commit_sha": "a" * 40,
            "result": "PASS",
            "actor_independent": True,
        },
    }
    return {"schema_version": "1.0.0", **payloads[kind]}


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


def test_gate_rejects_semantically_empty_artifact_and_file_store_resolves_content(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    item = bundle.evidence[0]
    empty = json.dumps(
        {
            "kind": item.kind,
            "deployment_id": item.deployment_id,
            "tenant_id": item.tenant_id,
            "commit_sha": item.commit_sha,
            "verified": item.verified,
            "observed_at": item.observed_at.isoformat().replace("+00:00", "Z"),
            "source": item.source,
            "payload": {"schema_version": "1.0.0"},
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    empty_item = EvidenceItem(
        item.kind,
        item.verified,
        item.observed_at,
        "sha256:" + hashlib.sha256(empty).hexdigest(),
        item.source,
        item.deployment_id,
        item.tenant_id,
        item.commit_sha,
    )
    changed = bundle.with_evidence((empty_item, *bundle.evidence[1:]))
    artifacts = {candidate.digest: _artifact_for(candidate) for candidate in changed.evidence[1:]}
    artifacts[empty_item.digest] = empty
    result = PilotAcceptanceGate(
        max_age=timedelta(days=1),
        evidence_resolver=InMemoryEvidenceArtifactResolver(artifacts),
    ).evaluate(changed, now=NOW)
    assert result.status is EvidenceStatus.BLOCKED
    assert "EVIDENCE_ARTIFACT_UNRESOLVED" in result.reasons

    content = _artifact_for(item)
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    (tmp_path / f"{digest.removeprefix('sha256:')}.json").write_bytes(content)
    assert FileEvidenceArtifactResolver(tmp_path).resolve(digest) == content
    assert FileEvidenceArtifactResolver(tmp_path).resolve("sha256:" + "0" * 64) is None


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
        deployment_id="pilot-eu-1",
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


def test_local_alert_evaluator_fires_without_high_cardinality_labels(tmp_path: Path) -> None:
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

    collector = PilotOperationalEvidenceCollector(baseline)
    assert collector.publish_tls(
        not_after=NOW + timedelta(days=30),
        hostname_verified=True,
        chain_verified=True,
        now=NOW,
    )
    assert collector.publish_recovery(
        {
            "schema_version": "1.0.0",
            "data_bytes": 4096,
            "verification_report_sha256": "sha256:" + "f" * 64,
            "audit_chains_valid": True,
            "exports_valid": True,
            "tenant_isolation_valid": True,
            "session_decryption_valid": True,
            "target_met": True,
        }
    )
    measured = baseline.render_prometheus()
    assert "backup_success 1" in measured
    assert "restore_success 1" in measured
    assert "tls_certificate_days_remaining 30" in measured

    tls_path = tmp_path / "tls.json"
    recovery_path = tmp_path / "recovery.json"
    tls_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "deployment_id": "pilot-eu-1",
                "environment": "controlled-pilot-test",
                "commit_sha": "a" * 40,
                "hostname": "pilot.example",
                "not_after": (NOW + timedelta(days=30)).isoformat(),
                "hostname_verified": True,
                "chain_verified": True,
            }
        ),
        encoding="utf-8",
    )
    recovery_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "deployment_id": "pilot-eu-1",
                "environment": "controlled-pilot-test",
                "commit_sha": "a" * 40,
                "data_bytes": 4096,
                "target_rpo_seconds": 60,
                "observed_rpo_seconds": 10,
                "target_rto_seconds": 120,
                "observed_rto_seconds": 30,
                "verification_report_sha256": "sha256:" + "f" * 64,
                "audit_chains_valid": True,
                "exports_valid": True,
                "tenant_isolation_valid": True,
                "session_decryption_valid": True,
                "target_met": True,
                "scope": "TEST_OBSERVATION_NOT_SERVICE_COMMITMENT",
            }
        ),
        encoding="utf-8",
    )
    from_files = InMemoryMetrics()
    initialize_pilot_metrics(from_files)
    assert PilotOperationalEvidenceCollector(from_files).load_files(
        tls_evidence=tls_path,
        recovery_evidence=recovery_path,
        now=NOW,
        expected_commit_sha="a" * 40,
        expected_environment="controlled-pilot-test",
        expected_deployment_id="pilot-eu-1",
        allowed_hosts=("pilot.example",),
    )
    assert from_files.gauge("backup_success") == 1
    assert not PilotOperationalEvidenceCollector(from_files).load_files(
        tls_evidence=tls_path,
        recovery_evidence=recovery_path,
        now=NOW + timedelta(days=31),
        expected_commit_sha="b" * 40,
        expected_environment="other-deployment",
        expected_deployment_id="pilot-eu-2",
        allowed_hosts=("other.example",),
    )
    assert from_files.gauge("backup_success") == 0
    assert from_files.gauge("tls_certificate_days_remaining") == 0

    outcomes = AssuranceOutcomeCollector(from_files)
    outcomes.record("REVIEW")
    outcomes.record("APPROVED")
    assert from_files.gauge("assurance_block_review_rate") == 0.5


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
