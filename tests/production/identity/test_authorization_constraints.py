import pytest

from decision_assurance.authorization import AuthorizationDenied, Permission, authorize
from decision_assurance.identity import ActorKind, Identity, Role
from decision_assurance.tenancy import TenantContext


def test_approval_permission_does_not_reclassify_a_service_as_human() -> None:
    human = Identity("approver", TenantContext("tenant-a"), Role.APPROVER, ActorKind.HUMAN)
    service = Identity("service", TenantContext("tenant-a"), Role.APPROVER, ActorKind.SERVICE)

    authorize(human, Permission.DECISION_APPROVE)
    authorize(service, Permission.DECISION_APPROVE)
    assert service.kind is ActorKind.SERVICE


def test_reviewer_and_system_administrator_are_explicit_least_privilege_roles() -> None:
    assert Role.REVIEWER is not Role.APPROVER
    assert Role.SYSTEM_ADMINISTRATOR is not Role.TENANT_ADMIN

    reviewer = Identity("reviewer", TenantContext("tenant-a"), Role.REVIEWER, ActorKind.HUMAN)
    authorize(reviewer, Permission.DECISION_READ)
    with pytest.raises(AuthorizationDenied):
        authorize(reviewer, Permission.DECISION_APPROVE)


def test_multiple_roles_union_permissions_without_changing_actor_identity() -> None:
    identity = Identity(
        "author-approver",
        TenantContext("tenant-a"),
        Role.GENERATOR,
        ActorKind.HUMAN,
        roles=frozenset({Role.GENERATOR, Role.APPROVER}),
    )

    authorize(identity, Permission.DECISION_CREATE)
    authorize(identity, Permission.DECISION_APPROVE)
    assert identity.actor_id == "author-approver"
    assert identity.kind is ActorKind.HUMAN


def test_keycloak_research_and_readonly_roles_are_least_privilege() -> None:
    operator = Identity(
        "researcher", TenantContext("tenant-a"), Role.RESEARCH_OPERATOR, ActorKind.HUMAN
    )
    readonly = Identity("reader", TenantContext("tenant-a"), Role.READONLY, ActorKind.HUMAN)

    authorize(operator, Permission.RESEARCH_CREATE)
    authorize(operator, Permission.RESEARCH_RETRY)
    with pytest.raises(AuthorizationDenied):
        authorize(operator, Permission.DECISION_APPROVE)
    authorize(readonly, Permission.DECISION_READ)
    with pytest.raises(AuthorizationDenied):
        authorize(readonly, Permission.RESEARCH_CREATE)


def test_tenant_admin_is_allowed_in_tenant_while_platform_admin_stays_bounded() -> None:
    tenant_admin = Identity(
        "tenant-admin", TenantContext("tenant-a"), Role.TENANT_ADMIN, ActorKind.HUMAN
    )
    platform_admin = Identity(
        "platform-admin", TenantContext("tenant-a"), Role.SYSTEM_ADMINISTRATOR, ActorKind.HUMAN
    )

    authorize(tenant_admin, Permission.DECISION_CREATE)
    with pytest.raises(AuthorizationDenied):
        authorize(platform_admin, Permission.DECISION_CREATE)
