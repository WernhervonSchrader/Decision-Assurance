import pytest

from decision_assurance.authorization import AuthorizationDenied, Permission, authorize
from decision_assurance.i18n import localize, select_locale
from decision_assurance.identity import ActorKind, Identity, Role, StaticTokenAuthenticator
from decision_assurance.tenancy import TenantContext


def test_tenant_context_rejects_empty_or_unsafe_identifiers() -> None:
    for value in ("", "../other", "tenant/other", " tenant"):
        with pytest.raises(ValueError):
            TenantContext(value)


def test_authenticator_establishes_identity_and_tenant_from_token() -> None:
    identity = Identity("alice", TenantContext("tenant-a"), Role.GENERATOR, ActorKind.HUMAN)
    auth = StaticTokenAuthenticator({"token-a": identity})
    assert auth.authenticate("token-a") == identity
    with pytest.raises(ValueError, match="INVALID_TOKEN"):
        auth.authenticate("unknown")


def test_authorization_is_centralized_and_fails_closed() -> None:
    generator = Identity("agent", TenantContext("tenant-a"), Role.GENERATOR, ActorKind.AGENT)
    authorize(generator, Permission.DECISION_CREATE)
    with pytest.raises(AuthorizationDenied):
        authorize(generator, Permission.AUDIT_READ)


def test_approver_permission_does_not_make_agent_human() -> None:
    agent = Identity("agent", TenantContext("tenant-a"), Role.APPROVER, ActorKind.AGENT)
    authorize(agent, Permission.DECISION_APPROVE)
    assert agent.kind is ActorKind.AGENT


@pytest.mark.parametrize(
    ("header", "expected"),
    [("de-DE,de;q=0.9", "de"), ("en-GB", "en"), ("fr-FR", "en"), (None, "en")],
)
def test_locale_selection_and_fallback(header: str | None, expected: str) -> None:
    assert select_locale(header) == expected


def test_machine_code_has_german_and_english_display() -> None:
    assert localize("NOT_FOUND", "de") == "Nicht gefunden."
    assert localize("NOT_FOUND", "en") == "Not found."
