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
    INTAKE_CREATE = "intake:create"
    INTAKE_READ = "intake:read"
    INTAKE_CONFIRM = "intake:confirm"
    INTAKE_COMPILE = "intake:compile"
    RESEARCH_CREATE = "research:create"
    RESEARCH_READ = "research:read"
    RESEARCH_RETRY = "research:retry"
    RESEARCH_CANCEL = "research:cancel"
    RESEARCH_HANDOFF = "research:handoff"
    RESEARCH_FORCE_REFRESH = "research:force-refresh"
    RESEARCH_AUDIT_READ = "research:audit-read"
    PILOT_EXPORT = "pilot:export"
    DATA_DELETE = "data:delete"
    LEGAL_HOLD_MANAGE = "legal-hold:manage"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.GENERATOR: frozenset(
        {
            Permission.DECISION_CREATE,
            Permission.DECISION_READ,
            Permission.REPORT_READ,
            Permission.INTAKE_CREATE,
            Permission.INTAKE_READ,
            Permission.RESEARCH_CREATE,
            Permission.RESEARCH_READ,
            Permission.RESEARCH_CANCEL,
            Permission.RESEARCH_HANDOFF,
        }
    ),
    Role.VALIDATOR: frozenset(
        {
            Permission.DECISION_READ,
            Permission.DECISION_EVALUATE,
            Permission.DECISION_VALIDATE,
            Permission.REPORT_READ,
            Permission.INTAKE_READ,
            Permission.INTAKE_CONFIRM,
            Permission.INTAKE_COMPILE,
            Permission.RESEARCH_CREATE,
            Permission.RESEARCH_READ,
            Permission.RESEARCH_RETRY,
            Permission.RESEARCH_CANCEL,
            Permission.RESEARCH_HANDOFF,
        }
    ),
    Role.APPROVER: frozenset(
        {
            Permission.DECISION_READ,
            Permission.DECISION_APPROVE,
            Permission.REPORT_READ,
            Permission.INTAKE_READ,
            Permission.INTAKE_CONFIRM,
            Permission.INTAKE_COMPILE,
            Permission.RESEARCH_READ,
            Permission.PILOT_EXPORT,
        }
    ),
    Role.AUDITOR: frozenset(
        {
            Permission.DECISION_READ,
            Permission.REPORT_READ,
            Permission.AUDIT_READ,
            Permission.INTAKE_READ,
            Permission.RESEARCH_READ,
            Permission.RESEARCH_AUDIT_READ,
            Permission.PILOT_EXPORT,
        }
    ),
    Role.REVIEWER: frozenset(
        {
            Permission.DECISION_READ,
            Permission.REPORT_READ,
            Permission.INTAKE_READ,
            Permission.RESEARCH_READ,
            Permission.RESEARCH_AUDIT_READ,
        }
    ),
    Role.TENANT_ADMIN: frozenset(Permission),
    Role.SYSTEM_ADMINISTRATOR: frozenset(
        {
            Permission.REPORT_READ,
            Permission.AUDIT_READ,
            Permission.RESEARCH_AUDIT_READ,
        }
    ),
    Role.RESEARCH_OPERATOR: frozenset(
        {
            Permission.DECISION_READ,
            Permission.REPORT_READ,
            Permission.RESEARCH_CREATE,
            Permission.RESEARCH_READ,
            Permission.RESEARCH_RETRY,
            Permission.RESEARCH_CANCEL,
            Permission.RESEARCH_HANDOFF,
            Permission.RESEARCH_FORCE_REFRESH,
            Permission.RESEARCH_AUDIT_READ,
        }
    ),
    Role.READONLY: frozenset(
        {
            Permission.DECISION_READ,
            Permission.REPORT_READ,
            Permission.INTAKE_READ,
            Permission.RESEARCH_READ,
        }
    ),
}


class AuthorizationDenied(PermissionError):
    pass


def authorize(identity: Identity, permission: Permission) -> None:
    if not any(permission in ROLE_PERMISSIONS.get(role, frozenset()) for role in identity.roles):
        raise AuthorizationDenied("FORBIDDEN")
