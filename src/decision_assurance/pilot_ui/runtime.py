from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI

from ..observability.metrics import InMemoryMetrics, initialize_pilot_metrics
from ..oidc.jwks import CachedJwksProvider
from ..oidc.mfa import MfaPolicy
from ..persistence.postgresql import PostgresConnectionProvider, PostgresSettings
from ..production.config import load_config
from ..production.contracts import OperatingMode
from ..production.ports import SecretProviderPort
from ..production.secrets import FileSecretProvider
from .api_client import HttpPilotApiClient
from .app import PilotUiSettings, create_pilot_ui_app
from .oidc import OidcBrowserClient
from .session_postgresql import PostgresSessionStore


def load_pilot_ui(
    environment: dict[str, str] | None = None,
    external_secrets: SecretProviderPort | None = None,
) -> FastAPI:
    values = environment if environment is not None else os.environ
    config_path = values.get("DA_CONFIG_PATH")
    if not config_path:
        raise RuntimeError("DA_CONFIG_PATH is required")
    config = load_config(Path(config_path), values)
    if config.operating_mode is not OperatingMode.CONTROLLED_PILOT:
        raise RuntimeError("CONTROLLED_PILOT_PROFILE_REQUIRED")
    pilot = config.controlled_pilot
    if pilot is None or config.oidc is None:
        raise RuntimeError("CONTROLLED_PILOT_CONFIGURATION_REQUIRED")
    api_url = values.get("DA_INTERNAL_API_URL")
    if not api_url or not api_url.startswith("http://"):
        raise RuntimeError("PILOT_INTERNAL_API_URL_REQUIRED")
    assets = Path(values.get("DA_PILOT_UI_ASSETS", "/app/ui-assets"))
    oidc_http = httpx.Client(follow_redirects=False, timeout=10.0)
    keys = CachedJwksProvider(
        issuer=config.oidc.policy.issuer,
        jwks_uri=config.oidc.jwks_uri,
        client=oidc_http,
    )
    browser_oidc = OidcBrowserClient(
        issuer=config.oidc.policy.issuer,
        client_id="decision-assurance-pilot-ui",
        authorization_endpoint=(
            config.oidc.policy.issuer.rstrip("/") + "/protocol/openid-connect/auth"
        ),
        token_endpoint=(config.oidc.policy.issuer.rstrip("/") + "/protocol/openid-connect/token"),
        redirect_uri=pilot.oidc_redirect_uri,
        keys=keys,
        http_client=oidc_http,
        algorithms=config.oidc.policy.algorithms,
    )
    api_client = HttpPilotApiClient(api_url, httpx.Client(follow_redirects=False, timeout=15.0))
    secrets = external_secrets
    if secrets is None:
        secret_directory = values.get("DA_SECRET_DIRECTORY")
        if not secret_directory:
            raise RuntimeError("PILOT_SECRET_PROVIDER_REQUIRED")
        secrets = FileSecretProvider(Path(secret_directory))
    database_dsn = secrets.resolve(config.database_dsn_secret)
    session_store = PostgresSessionStore(
        PostgresConnectionProvider(PostgresSettings(database_dsn)),
        session_pepper=secrets.resolve(pilot.session_pepper_secret).value.encode(),
        envelope_key=secrets.resolve(pilot.session_envelope_key_secret).value.encode(),
        required_mfa_policy_version="controlled-pilot-mfa-v1",
    )
    runtime_metrics = InMemoryMetrics()
    initialize_pilot_metrics(runtime_metrics)
    return create_pilot_ui_app(
        PilotUiSettings(
            allowed_hosts=pilot.allowed_hosts,
            trusted_proxy_cidrs=pilot.trusted_proxy_cidrs,
            post_logout_redirect_uri=pilot.post_logout_redirect_uri,
            asset_directory=assets,
            oidc_end_session_endpoint=(
                config.oidc.policy.issuer.rstrip("/") + "/protocol/openid-connect/logout"
            ),
            mfa_policy=MfaPolicy(
                version="controlled-pilot-mfa-v1",
                required_roles=frozenset(
                    {"SYSTEM_ADMINISTRATOR", "TENANT_ADMIN", "APPROVER", "AUDITOR"}
                ),
                allowed_acr=frozenset({"urn:da:pilot:mfa", "2"}),
                allowed_methods=frozenset({"otp", "webauthn"}),
                max_auth_age=timedelta(minutes=15),
            ),
        ),
        browser_oidc,
        api_client,
        session_store=session_store,
        metrics=runtime_metrics,
    )


def main() -> None:
    uvicorn.run(
        load_pilot_ui(),
        host=os.getenv("DA_PILOT_UI_HOST", "127.0.0.1"),
        port=int(os.getenv("DA_PILOT_UI_PORT", "8080")),
        proxy_headers=False,
        server_header=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
