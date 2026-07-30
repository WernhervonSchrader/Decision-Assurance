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
            "external_processing_locations": [],
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

