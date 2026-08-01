from __future__ import annotations

import os
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI

from ..observability.metrics import InMemoryMetrics
from ..oidc.jwks import CachedJwksProvider
from ..production.config import load_config
from ..production.contracts import OperatingMode
from .api_client import HttpPilotApiClient
from .app import PilotUiSettings, create_pilot_ui_app
from .oidc import OidcBrowserClient


def load_pilot_ui(environment: dict[str, str] | None = None) -> FastAPI:
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
    return create_pilot_ui_app(
        PilotUiSettings(
            allowed_hosts=pilot.allowed_hosts,
            trusted_proxy_cidrs=pilot.trusted_proxy_cidrs,
            post_logout_redirect_uri=pilot.post_logout_redirect_uri,
            asset_directory=assets,
            oidc_end_session_endpoint=(
                config.oidc.policy.issuer.rstrip("/") + "/protocol/openid-connect/logout"
            ),
        ),
        browser_oidc,
        api_client,
        metrics=InMemoryMetrics(),
    )


def main() -> None:
    uvicorn.run(
        load_pilot_ui(),
        host=os.getenv("DA_PILOT_UI_HOST", "127.0.0.1"),
        port=int(os.getenv("DA_PILOT_UI_PORT", "8080")),
        proxy_headers=False,
        server_header=False,
    )


if __name__ == "__main__":
    main()
