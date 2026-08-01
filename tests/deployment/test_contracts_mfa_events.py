from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from decision_assurance.events.registry import EventEnvelope, EventRegistry, EventVersionError
from decision_assurance.oidc.mfa import MfaEvidence, MfaPolicy, MfaRequired
from decision_assurance.provenance.config import SigningMode, SigningSettings

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


def test_three_signing_modes_are_reference_only_and_fail_closed() -> None:
    development = SigningSettings.from_mapping(
        {"mode": "development", "key_id": "dev-key", "key_reference": ".secrets/export.pem"}
    )
    pilot = SigningSettings.from_mapping(
        {
            "mode": "controlled-pilot",
            "key_id": "pilot-key",
            "key_reference": "/run/secrets/export-key",
        }
    )
    adapter = SigningSettings.from_mapping(
        {"mode": "production-adapter", "key_id": "kms-key", "key_reference": "kms-ref://tenant/key"}
    )
    assert development.mode is SigningMode.DEVELOPMENT
    assert pilot.mode is SigningMode.CONTROLLED_PILOT
    assert adapter.mode is SigningMode.PRODUCTION_ADAPTER
    for invalid in (
        {"mode": "cloud", "key_id": "x", "key_reference": "x"},
        {"mode": "development", "key_id": "x", "private_key": "secret"},
        {"mode": "controlled-pilot", "key_id": "x", "key_reference": ".secrets/key"},
    ):
        with pytest.raises(ValueError):
            SigningSettings.from_mapping(invalid)


def test_event_registry_rejects_unknown_versions_and_records_lossless_migration() -> None:
    registry = EventRegistry()
    current = EventEnvelope(
        event_type="deployment.evidence-created",
        schema_version="1.0.0",
        event_id="event-1",
        occurred_at=NOW,
        tenant_id="tenant-a",
        actor_id="operator-a",
        correlation_id="corr-1",
        source_component="deployment-evidence",
        payload={"deployment_id": "pilot-1"},
    )
    assert registry.parse(current.as_dict()).event_id == "event-1"
    unknown = {**current.as_dict(), "schema_version": "9.0.0"}
    with pytest.raises(EventVersionError, match="EVENT_VERSION_UNSUPPORTED"):
        registry.parse(unknown)
    with pytest.raises(EventVersionError, match="EVENT_TYPE_UNSUPPORTED"):
        registry.parse({**current.as_dict(), "event_type": "unknown.event"})

    legacy = {**current.as_dict(), "schema_version": "0.9.0", "source": "deployment-evidence"}
    legacy.pop("source_component")
    migrated = registry.migrate(legacy, target_version="1.0.0")
    assert migrated.event.source_component == "deployment-evidence"
    assert migrated.source_version == "0.9.0"
    assert migrated.target_version == "1.0.0"
    assert migrated.original_hash.startswith("sha256:")


def test_mfa_policy_uses_validated_context_and_policy_version() -> None:
    policy = MfaPolicy(
        version="mfa-2",
        required_roles=frozenset({"APPROVER", "TENANT_ADMIN", "AUDITOR", "SYSTEM_ADMINISTRATOR"}),
        allowed_acr=frozenset({"urn:da:pilot:mfa"}),
        allowed_methods=frozenset({"otp", "webauthn"}),
        max_auth_age=timedelta(minutes=15),
    )
    evidence = MfaEvidence(
        acr="urn:da:pilot:mfa",
        amr=("pwd", "webauthn"),
        authenticated_at=NOW - timedelta(minutes=2),
        policy_version="mfa-2",
    )
    policy.require(frozenset({"APPROVER"}), evidence, now=NOW)
    policy.require(frozenset({"GENERATOR"}), None, now=NOW)

    for invalid in (
        None,
        MfaEvidence("urn:da:pilot:pwd", ("pwd",), NOW, "mfa-2"),
        MfaEvidence("urn:da:pilot:mfa", ("pwd", "otp"), NOW, "mfa-1"),
        MfaEvidence("urn:da:pilot:mfa", ("pwd", "otp"), NOW - timedelta(hours=1), "mfa-2"),
    ):
        with pytest.raises(MfaRequired):
            policy.require(frozenset({"APPROVER"}), invalid, now=NOW)
