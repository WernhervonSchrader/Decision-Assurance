from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from decision_assurance.api.runtime import load_runtime
from decision_assurance.oidc.authenticator import OidcAuthenticator
from decision_assurance.persistence.postgresql import PostgresConnectionProvider
from decision_assurance.production.contracts import OperatingMode, SecretReference, SecretValue
from decision_assurance.repositories.postgresql import PostgresDecisionRepository

ROOT = Path(__file__).parents[3]


class FakeExternalSecrets:
    def resolve(self, reference: SecretReference) -> SecretValue:
        values = {
            "decision-assurance-database-dsn": "postgresql://runtime.invalid/decision-assurance",
            "decision-assurance-worker-database-dsn": (
                "postgresql://worker.invalid/decision-assurance"
            ),
            "openai-key": "openai-canary-value",
            "firecrawl-key": "firecrawl-canary-value",
        }
        return SecretValue(values[reference.name])


@pytest.mark.parametrize(
    ("mode", "config_name", "search_host", "extract_host"),
    [
        (
            OperatingMode.LOCAL,
            "local.example.json",
            "openai-api.local.example",
            "research-extract.local.example",
        ),
        (
            OperatingMode.EU_MANAGED,
            "eu-managed.example.json",
            "openai-api.eu.example",
            "research-extract.eu.example",
        ),
    ],
)
def test_operating_profile_builds_the_same_fail_closed_runtime(
    mode: OperatingMode,
    config_name: str,
    search_host: str,
    extract_host: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    role_checks: list[bool] = []
    monkeypatch.setattr(
        PostgresConnectionProvider,
        "assert_safe_application_role",
        lambda self: role_checks.append(True),
    )

    app = load_runtime(
        {
            "DA_CONFIG_PATH": str(ROOT / "config" / "deployment" / config_name),
            "DA_OPENAI_API_KEY_SECRET_REF": "openai-key",
            "DA_FIRECRAWL_API_KEY_SECRET_REF": "firecrawl-key",
            "OPENAI_BASE_URL": f"https://{search_host}",
            "FIRECRAWL_BASE_URL": f"https://{extract_host}",
            "DA_VERSION": "0.5.0",
            "DA_COMMIT_SHA": "a" * 40,
            "DA_BUILD_TIMESTAMP": "2026-07-30T10:00:00Z",
        },
        external_secrets=FakeExternalSecrets(),
        oidc_http_client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(503))
        ),
    )

    assert isinstance(app.state.repository, PostgresDecisionRepository)
    assert isinstance(app.state.authenticator, OidcAuthenticator)
    assert app.state.operating_mode is mode
    assert app.state.data_residency is not None
    assert app.state.research_submission_service is not None
    assert role_checks == [True]
    assert "canary-value" not in repr(app.state)


def test_provider_residency_conflict_fails_before_secret_or_adapter_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_resolutions: list[str] = []

    class TrackingSecrets(FakeExternalSecrets):
        def resolve(self, reference: SecretReference) -> SecretValue:
            secret_resolutions.append(reference.name)
            return super().resolve(reference)

    monkeypatch.setattr(
        PostgresConnectionProvider,
        "assert_safe_application_role",
        lambda self: pytest.fail("database adapter must not be constructed"),
    )

    with pytest.raises(ValueError, match="PROVIDER_EGRESS_UNDECLARED"):
        load_runtime(
            {
                "DA_CONFIG_PATH": str(ROOT / "config" / "deployment" / "eu-managed.example.json"),
                "OPENAI_BASE_URL": "https://undeclared-provider.example",
                "FIRECRAWL_BASE_URL": "https://research-extract.eu.example",
            },
            external_secrets=TrackingSecrets(),
        )

    assert secret_resolutions == []
