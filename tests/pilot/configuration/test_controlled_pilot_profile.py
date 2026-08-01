from __future__ import annotations

from copy import deepcopy

import pytest

from decision_assurance.production.config import RuntimeConfig
from decision_assurance.production.contracts import OperatingMode


def controlled_pilot_mapping() -> dict[str, object]:
    return {
        "profile": "production",
        "operating_mode": "controlled-pilot",
        "data_residency": {
            "storage_locations": ["DE"],
            "processing_locations": ["DE"],
            "backup_locations": ["DE"],
            "support_access_locations": ["DE"],
            "external_processing_locations": ["DE"],
            "evidence_refs": ["https://compliance.example/pilot-residency"],
        },
        "database_backend": "postgresql",
        "authentication_mode": "oidc",
        "secret_provider": "external",
        "database_dsn_secret": "database-dsn",
        "worker_database_dsn_secret": "worker-database-dsn",
        "oidc": {
            "issuer": "https://identity.pilot.example/realms/decision-assurance",
            "audience": "decision-assurance",
            "jwks_uri": "https://identity.pilot.example/realms/decision-assurance/protocol/openid-connect/certs",
            "algorithms": ["RS256"],
            "authorized_parties": ["decision-assurance-pilot-ui"],
            "required_scopes": ["da.api"],
        },
        "egress_allowed_hosts": ["provider.pilot.example"],
        "provider_egress": [
            {
                "provider": "provider",
                "service": "search",
                "host": "provider.pilot.example",
                "processing_location": "DE",
                "confirmed_processing_locations": ["DE"],
                "tenant_ids": ["pilot-tenant"],
                "attestation": {
                    "evidence_id": "pilot-provider-evidence",
                    "evidence_type": "SIGNED_PROVIDER_ATTESTATION",
                    "evidence_ref": "https://compliance.example/provider",
                    "issuer": "provider",
                    "issued_at": "2026-01-01T00:00:00Z",
                    "valid_from": "2026-01-01T00:00:00Z",
                    "expires_at": "2027-01-01T00:00:00Z",
                    "verification_status": "VERIFIED",
                    "verified_at": "2026-01-01T00:00:00Z",
                    "verified_by": "security-review",
                    "document_hash": "sha256:" + "a" * 64,
                },
            }
        ],
        "worker": {},
        "controlled_pilot": {
            "public_base_url": "https://research.pilot.example",
            "oidc_redirect_uri": "https://research.pilot.example/auth/callback",
            "post_logout_redirect_uri": "https://research.pilot.example/",
            "allowed_hosts": ["research.pilot.example"],
            "trusted_proxy_cidrs": ["172.30.0.0/24"],
            "audit_persistence": True,
            "backup_configuration_ref": "pilot-backup-policy-v1",
            "lifecycle_pseudonymization_secret": "pilot-lifecycle-pepper",
            "session_pepper_secret": "pilot-session-pepper",
            "session_envelope_key_secret": "pilot-session-envelope-key",
            "export_signing": {
                "mode": "controlled-pilot",
                "key_id": "pilot-export-signing-2026-01",
                "key_reference": "/run/secrets/pilot-export-signing-key",
            },
            "retention_days": 30,
            "pilot_tenant": "pilot-tenant",
            "health_path": "/health/live",
            "readiness_path": "/health/ready",
        },
    }


def test_controlled_pilot_profile_is_explicit_and_typed() -> None:
    config = RuntimeConfig.from_mapping(controlled_pilot_mapping())

    assert config.operating_mode is OperatingMode.CONTROLLED_PILOT
    assert config.controlled_pilot is not None
    assert config.controlled_pilot.pilot_tenant == "pilot-tenant"
    assert config.controlled_pilot.allowed_hosts == ("research.pilot.example",)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda raw: raw.pop("controlled_pilot"), "CONTROLLED_PILOT_CONFIGURATION_REQUIRED"),
        (
            lambda raw: raw["controlled_pilot"].update(  # type: ignore[union-attr]
                {"public_base_url": "http://research.pilot.example"}
            ),
            "PILOT_HTTPS_REQUIRED",
        ),
        (
            lambda raw: raw["controlled_pilot"].update(  # type: ignore[union-attr]
                {"oidc_redirect_uri": "https://localhost/auth/callback"}
            ),
            "PILOT_LOOPBACK_FORBIDDEN",
        ),
        (
            lambda raw: raw["controlled_pilot"].update({"allowed_hosts": []}),  # type: ignore[union-attr]
            "PILOT_ALLOWED_HOSTS_REQUIRED",
        ),
        (
            lambda raw: raw["controlled_pilot"].update(  # type: ignore[union-attr]
                {"trusted_proxy_cidrs": []}
            ),
            "PILOT_TRUSTED_PROXY_REQUIRED",
        ),
        (
            lambda raw: raw["controlled_pilot"].update(  # type: ignore[union-attr]
                {"audit_persistence": False}
            ),
            "PILOT_AUDIT_PERSISTENCE_REQUIRED",
        ),
        (
            lambda raw: raw["controlled_pilot"].update(  # type: ignore[union-attr]
                {"backup_configuration_ref": "example"}
            ),
            "PILOT_BACKUP_CONFIGURATION_REQUIRED",
        ),
        (
            lambda raw: raw["controlled_pilot"].update({"retention_days": 0}),  # type: ignore[union-attr]
            "PILOT_RETENTION_REQUIRED",
        ),
        (
            lambda raw: raw["controlled_pilot"].update({"pilot_tenant": ""}),  # type: ignore[union-attr]
            "PILOT_TENANT_REQUIRED",
        ),
        (
            lambda raw: raw["controlled_pilot"].update({"health_path": ""}),  # type: ignore[union-attr]
            "PILOT_HEALTH_PROBES_REQUIRED",
        ),
    ],
)
def test_controlled_pilot_fails_closed_for_missing_prerequisite(mutation, reason: str) -> None:  # type: ignore[no-untyped-def]
    raw = deepcopy(controlled_pilot_mapping())
    mutation(raw)

    with pytest.raises(ValueError, match=reason):
        RuntimeConfig.from_mapping(raw)


def test_non_pilot_profile_rejects_pilot_configuration() -> None:
    raw = controlled_pilot_mapping()
    raw["operating_mode"] = "eu-managed"

    with pytest.raises(ValueError, match="CONTROLLED_PILOT_PROFILE_REQUIRED"):
        RuntimeConfig.from_mapping(raw)
