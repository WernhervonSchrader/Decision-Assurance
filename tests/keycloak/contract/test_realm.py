from __future__ import annotations

import json
from pathlib import Path

REALM_PATH = Path("integrations/keycloak/decision-assurance-realm.json")
EXPECTED_ROLES = {
    "da_admin",
    "tenant_admin",
    "decision_author",
    "decision_reviewer",
    "decision_approver",
    "auditor",
    "research_operator",
    "readonly",
}


def _realm() -> dict[str, object]:
    return json.loads(REALM_PATH.read_text(encoding="utf-8"))


def test_realm_is_secret_free_reproducible_and_bounded() -> None:
    realm = _realm()
    assert realm["realm"] == "decision-assurance"
    assert realm["enabled"] is True
    assert realm["sslRequired"] == "external"
    assert realm["accessTokenLifespan"] == 300
    assert realm["revokeRefreshToken"] is True
    assert realm["refreshTokenMaxReuse"] == 0
    assert realm.get("users", []) == []
    raw = REALM_PATH.read_text(encoding="utf-8")
    assert "client-secret" not in raw.casefold()
    assert '"secret"' not in raw.casefold()


def test_realm_roles_are_exact_and_clients_are_least_privilege() -> None:
    realm = _realm()
    roles = {item["name"] for item in realm["roles"]["realm"]}  # type: ignore[index]
    assert roles == EXPECTED_ROLES
    scope_mappings = realm["scopeMappings"]  # type: ignore[index]
    assert len(scope_mappings) == 1
    assert scope_mappings[0]["clientScope"] == "roles"
    assert set(scope_mappings[0]["roles"]) == EXPECTED_ROLES
    clients = {item["clientId"]: item for item in realm["clients"]}  # type: ignore[index]
    assert set(clients) == {
        "decision-assurance-api",
        "decision-assurance-ui",
        "decision-assurance-e2e",
    }

    api = clients["decision-assurance-api"]
    assert api["publicClient"] is False
    assert api["directAccessGrantsEnabled"] is False
    assert api["serviceAccountsEnabled"] is False
    assert api["standardFlowEnabled"] is False

    for client_id in ("decision-assurance-ui", "decision-assurance-e2e"):
        client = clients[client_id]
        assert client["publicClient"] is True
        assert client["standardFlowEnabled"] is True
        assert client["directAccessGrantsEnabled"] is False
        assert client["serviceAccountsEnabled"] is False
        assert client["attributes"]["pkce.code.challenge.method"] == "S256"
        assert all("*" not in uri for uri in client["redirectUris"])
        assert all("*" not in uri for uri in client["webOrigins"])
        assert all(
            "*" not in uri for uri in client["attributes"]["post.logout.redirect.uris"].split("##")
        )


def test_realm_emits_tenant_actor_roles_scope_and_api_audience() -> None:
    realm = _realm()
    scopes = {item["name"]: item for item in realm["clientScopes"]}  # type: ignore[index]
    assert {"basic", "da.api", "roles"}.issubset(scopes)
    basic_mappers = scopes["basic"]["protocolMappers"]
    assert any(item["protocolMapper"] == "oidc-sub-mapper" for item in basic_mappers)
    mappers = scopes["da.api"]["protocolMappers"]
    mapper_names = {item["name"] for item in mappers}
    assert {"tenant_id", "actor_kind", "organization", "api-audience"}.issubset(mapper_names)
    audience = next(item for item in mappers if item["name"] == "api-audience")
    assert audience["config"]["included.client.audience"] == "decision-assurance-api"


def test_realm_manages_security_identity_attributes_as_admin_only() -> None:
    realm = _realm()
    providers = realm["components"]["org.keycloak.userprofile.UserProfileProvider"]  # type: ignore[index]
    assert len(providers) == 1
    raw_config = providers[0]["config"]["kc.user.profile.config"][0]
    profile = json.loads(raw_config)
    assert "unmanagedAttributePolicy" not in profile
    attributes = {item["name"]: item for item in profile["attributes"]}
    assert {"username", "email", "firstName", "lastName"}.issubset(attributes)
    assert {"tenant_id", "actor_kind", "organization"}.issubset(attributes)
    for attribute in (attributes[name] for name in ("tenant_id", "actor_kind", "organization")):
        assert attribute["permissions"] == {"view": ["admin"], "edit": ["admin"]}
