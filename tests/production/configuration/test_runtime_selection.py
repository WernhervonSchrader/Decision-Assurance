import json
from pathlib import Path

import httpx
import pytest

from decision_assurance.api.runtime import load_runtime
from decision_assurance.oidc.authenticator import OidcAuthenticator
from decision_assurance.persistence.postgresql import PostgresConnectionProvider
from decision_assurance.production.contracts import SecretReference, SecretValue
from decision_assurance.repositories.postgresql import PostgresDecisionRepository


class FakeExternalSecrets:
    def resolve(self, reference: SecretReference) -> SecretValue:
        values = {
            "database-dsn": "postgresql://runtime.invalid/decision-assurance",
            "worker-database-dsn": "postgresql://worker.invalid/decision-assurance",
            "brave-key": "brave-canary-value",
            "firecrawl-key": "firecrawl-canary-value",
        }
        return SecretValue(values[reference.name])


def test_configured_production_runtime_selects_only_production_adapters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    role_checks: list[bool] = []
    monkeypatch.setattr(
        PostgresConnectionProvider,
        "assert_safe_application_role",
        lambda self: role_checks.append(True),
    )
    config = {
        "profile": "production",
        "operating_mode": "local",
        "data_residency": {
            "storage_locations": ["local"],
            "processing_locations": ["local"],
            "backup_locations": ["local"],
            "support_access_locations": ["local"],
            "external_processing_locations": [],
            "evidence_refs": [],
        },
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
        "egress_allowed_hosts": ["api.search.brave.com", "api.firecrawl.dev"],
        "worker": {},
    }
    path = tmp_path / "production.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    app = load_runtime(
        {
            "DA_CONFIG_PATH": str(path),
            "DA_BRAVE_API_KEY_SECRET_REF": "brave-key",
            "DA_FIRECRAWL_API_KEY_SECRET_REF": "firecrawl-key",
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
    assert app.state.research_submission_service is not None
    assert role_checks == [True]
    assert "canary-value" not in repr(app.state)
