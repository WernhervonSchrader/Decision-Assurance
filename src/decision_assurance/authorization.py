from __future__ import annotations

from enum import Enum

from .identity import Identity, Role


class Permission(str, Enum):
    DECISION_CREATE = "decision:create"
    DECISION_READ = "decision:read"
    DECISION_EVALUATE = "decision:evaluate"
    DECISION_VALIDATE = "decision:validate"
    DECISION_APPROVE = "decision:approve"
    REPORT_READ = "report:read"
    AUDIT_READ = "audit:read"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.GENERATOR: frozenset({Permission.DECISION_CREATE, Permission.DECISION_READ, Permission.REPORT_READ}),
    Role.VALIDATOR: frozenset({Permission.DECISION_READ, Permission.DECISION_EVALUATE, Permission.DECISION_VALIDATE, Permission.REPORT_READ}),
    Role.APPROVER: frozenset({Permission.DECISION_READ, Permission.DECISION_APPROVE, Permission.REPORT_READ}),
    Role.AUDITOR: frozenset({Permission.DECISION_READ, Permission.REPORT_READ, Permission.AUDIT_READ}),
    Role.TENANT_ADMIN: frozenset(Permission),
}


class AuthorizationDenied(PermissionError):
    pass


def authorize(identity: Identity, permission: Permission) -> None:
    if permission not in ROLE_PERMISSIONS.get(identity.role, frozenset()):
        raise AuthorizationDenied("FORBIDDEN")

