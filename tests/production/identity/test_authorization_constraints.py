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
