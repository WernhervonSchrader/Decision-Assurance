from __future__ import annotations

from copy import deepcopy

import pytest

from decision_assurance.production.config import RuntimeConfig
from decision_assurance.production.contracts import OperatingMode


def _base(mode: str) -> dict[str, object]:
    residency: dict[str, object]
    if mode == "local":
        residency = {
            "storage_locations": ["local"],
            "processing_locations": ["local"],
            "backup_locations": ["local"],
            "support_access_locations": ["local"],
            "external_processing_locations": ["local"],
            "evidence_refs": [],
        }
    else:
        residency = {
            "storage_locations": ["DE"],
            "processing_locations": ["DE", "IE"],
            "backup_locations": ["DE"],
            "support_access_locations": ["DE", "NL"],
            "external_processing_locations": ["DE"],
            "evidence_refs": [
                "https://compliance.example/residency",
                "https://compliance.example/subprocessors",
            ],
        }
    return {
        "profile": "production",
        "operating_mode": mode,
        "data_residency": residency,
        "database_backend": "postgresql",
        "authentication_mode": "oidc",
        "secret_provider": "external",
        "database_dsn_secret": "database-dsn",
        "worker_database_dsn_secret": "worker-database-dsn",
        "oidc": {
            "issuer": "https://identity.example",
            "audience": "decision-assurance",
            "jwks_uri": "https://identity.example/jwks.json",
            "algorithms": ["RS256"],
        },
        "egress_allowed_hosts": ["provider.example"],
        "provider_egress": [
            {
                "provider": "provider",
                "service": "search",
                "host": "provider.example",
                "processing_location": "local" if mode == "local" else "DE",
                "confirmed_processing_locations": [],
                "tenant_ids": ["*"],
                "attestation": {
                    "evidence_id": "provider-attestation",
                    "evidence_type": "OPERATOR_SELF_DECLARATION",
                    "evidence_ref": "https://evidence.example/provider",
                    "issuer": "operator",
                    "issued_at": "2026-01-01T00:00:00Z",
                    "valid_from": "2026-01-01T00:00:00Z",
                    "expires_at": "2027-01-01T00:00:00Z",
                    "verification_status": "UNVERIFIED",
                    "verified_at": None,
                    "verified_by": None,
                    "document_hash": None,
                },
            }
        ],
        "worker": {},
    }


@pytest.mark.parametrize("mode", ["local", "eu-managed"])
def test_production_operating_profiles_are_typed_and_complete(mode: str) -> None:
    config = RuntimeConfig.from_mapping(_base(mode))

    assert config.operating_mode is OperatingMode(mode)
    assert config.data_residency is not None


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda raw: raw.pop("operating_mode"), "OPERATING_MODE_REQUIRED"),
        (lambda raw: raw.pop("data_residency"), "DATA_RESIDENCY_POLICY_REQUIRED"),
        (
            lambda raw: raw["data_residency"].update({"storage_locations": ["US"]}),  # type: ignore[union-attr]
            "EU_DATA_LOCATION_REQUIRED",
        ),
        (
            lambda raw: raw["data_residency"].update({"backup_locations": []}),  # type: ignore[union-attr]
            "DATA_LOCATION_REQUIRED",
        ),
        (
            lambda raw: raw["data_residency"].update(  # type: ignore[union-attr]
                {"support_access_locations": ["US"]}
            ),
            "EU_DATA_LOCATION_REQUIRED",
        ),
        (
            lambda raw: raw["data_residency"].update({"evidence_refs": []}),  # type: ignore[union-attr]
            "EU_RESIDENCY_EVIDENCE_REQUIRED",
        ),
        (
            lambda raw: raw["data_residency"].update(  # type: ignore[union-attr]
                {"evidence_refs": ["http://compliance.example/residency"]}
            ),
            "INVALID_RESIDENCY_EVIDENCE_REFERENCE",
        ),
    ],
)
def test_eu_managed_rejects_incomplete_or_non_eu_policy(mutation, reason: str) -> None:  # type: ignore[no-untyped-def]
    raw = deepcopy(_base("eu-managed"))
    mutation(raw)

    with pytest.raises(ValueError, match=reason):
        RuntimeConfig.from_mapping(raw)


@pytest.mark.parametrize(
    "field",
    [
        "storage_locations",
        "processing_locations",
        "backup_locations",
        "support_access_locations",
    ],
)
def test_local_rejects_locations_outside_its_operator_boundary(field: str) -> None:
    raw = deepcopy(_base("local"))
    raw["data_residency"][field] = ["DE"]  # type: ignore[index]

    with pytest.raises(ValueError, match="LOCAL_DATA_BOUNDARY_REQUIRED"):
        RuntimeConfig.from_mapping(raw)


def test_operating_profile_rejects_unknown_fields() -> None:
    raw = deepcopy(_base("eu-managed"))
    raw["data_residency"]["silent_fallback"] = True  # type: ignore[index]

    with pytest.raises(ValueError, match="UNKNOWN_DATA_RESIDENCY_FIELD"):
        RuntimeConfig.from_mapping(raw)


def test_local_profile_accepts_only_local_provider_processing() -> None:
    config = RuntimeConfig.from_mapping(_base("local"))

    config.validate_provider_urls(("https://provider.example/search",))


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda raw: raw["data_residency"].update(  # type: ignore[union-attr]
                {"external_processing_locations": []}
            ),
            "PROVIDER_PROCESSING_LOCATION_UNDECLARED",
        ),
        (
            lambda raw: raw["provider_egress"][0].update(  # type: ignore[index,union-attr]
                {"processing_location": "US"}
            ),
            "LOCAL_PROVIDER_PROCESSING_REQUIRED",
        ),
        (
            lambda raw: raw.update({"egress_allowed_hosts": ["other.example"]}),
            "PROVIDER_EGRESS_ALLOWLIST_MISMATCH",
        ),
        (
            lambda raw: raw["provider_egress"][0].update(  # type: ignore[index,union-attr]
                {"tenant_id": "tenant-a"}
            ),
            "UNKNOWN_PROVIDER_EGRESS_FIELD",
        ),
    ],
)
def test_local_profile_rejects_undeclared_external_or_tenant_specific_egress(
    mutation,
    reason: str,  # type: ignore[no-untyped-def]
) -> None:
    raw = deepcopy(_base("local"))
    mutation(raw)

    with pytest.raises(ValueError, match=reason):
        RuntimeConfig.from_mapping(raw)


def test_eu_managed_accepts_declared_eu_provider() -> None:
    config = RuntimeConfig.from_mapping(_base("eu-managed"))

    config.validate_provider_urls(("https://provider.example/search",))


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda raw: raw["provider_egress"][0].update(  # type: ignore[index,union-attr]
                {"processing_location": "US"}
            ),
            "EU_PROVIDER_PROCESSING_REQUIRED",
        ),
        (
            lambda raw: raw["provider_egress"][0].update(  # type: ignore[index,union-attr]
                {"processing_location": "IE"}
            ),
            "PROVIDER_PROCESSING_LOCATION_UNDECLARED",
        ),
    ],
)
def test_eu_managed_rejects_provider_outside_allowed_or_declared_regions(
    mutation,
    reason: str,  # type: ignore[no-untyped-def]
) -> None:
    raw = deepcopy(_base("eu-managed"))
    mutation(raw)

    with pytest.raises(ValueError, match=reason):
        RuntimeConfig.from_mapping(raw)


def test_runtime_rejects_actual_provider_url_not_declared_by_profile() -> None:
    config = RuntimeConfig.from_mapping(_base("eu-managed"))

    with pytest.raises(ValueError, match="PROVIDER_EGRESS_UNDECLARED"):
        config.validate_provider_urls(("https://undeclared.example/search",))
