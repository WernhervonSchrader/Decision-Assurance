# Decision Assurance API v0.2 — Design Specification

**Status:** approved implementation specification  
**Product status:** Public Draft v0.2; no standards, certification, compliance or legal-safety claim

## Objective and users

Expose the deterministic Decision Assurance domain engine through a secure,
tenant-aware HTTP API. Enterprise applications and AI agents submit cases;
validators evaluate them; explicitly authorized humans approve or block them;
auditors read immutable reports and audit history.

Success is measurable: two isolated tenants can complete the same case IDs
without information leakage; an agent cannot simulate human approval; German
and English errors are available; retrying a write with the same idempotency key
does not duplicate state or events; the complete DRAFT-to-terminal journey runs
locally and in CI without an LLM.

## Scope

v0.2 includes assessment intake, case retrieval, evaluation, transition,
Assurance Report and audit retrieval. It uses SQLite for a zero-service local
reference deployment behind a repository abstraction. PostgreSQL and row-level
security are the production deployment target, documented but not falsely
claimed as implemented. Authentication is an injectable trusted-identity
boundary: production deployments must connect a verified OIDC/JWT gateway; the
reference API accepts no self-asserted tenant from request bodies.

Browser UI, password storage, email, external policy retrieval, production OIDC
key verification, distributed rate limiting and deployment automation are out
of scope for this increment.

## Interfaces

All endpoints are under `/v1`. JSON requests reject unknown fields. Protected
requests require `Authorization: Bearer <test-or-gateway-token>` and establish
tenant and actor from the authentication adapter.

| Method and path | Permission | Result |
| --- | --- | --- |
| `POST /v1/decisions` | `decision:create` | Creates a tenant-owned Decision File; idempotent. |
| `GET /v1/decisions/{id}` | `decision:read` | Returns only the current tenant's case. |
| `POST /v1/decisions/{id}/evaluate` | `decision:evaluate` | Runs deterministic governance and persists report/audit. |
| `POST /v1/decisions/{id}/transitions` | status-dependent | Applies Transition Policy using authenticated actor. |
| `GET /v1/decisions/{id}/report` | `report:read` | Returns latest Assurance Report. |
| `GET /v1/decisions/{id}/audit` | `audit:read` | Returns ordered tenant-scoped events with bounded pagination. |
| `GET /health/live`, `GET /health/ready` | public | Process and storage readiness without sensitive detail. |

Errors use `{code, message, correlation_id, details}`. `code` is stable English
machine language; `message` is localized from `Accept-Language`, with English
fallback. Audit records store codes, not localized prose.

## Roles and authorization

Roles are `GENERATOR`, `VALIDATOR`, `APPROVER`, `AUDITOR`, `TENANT_ADMIN`.
Permissions are centralized. Object lookup always includes tenant identity.
Approvals require an authenticated human identity and separation from generator
and validator. A missing, invalid or unsupported identity fails closed.

## Tenant and data model

Every business row contains `tenant_id`. Primary uniqueness is
`(tenant_id, decision_id)`. Idempotency uniqueness is
`(tenant_id, actor_id, operation, idempotency_key)`. Audit rows include tenant,
actor, action, target, correlation ID, reason codes, previous hash and event
hash. Sensitive request bodies and bearer tokens are never logged.

## Localization and versions

Interface locales are `en` and `de`; unsupported or absent locales fall back to
`en`. Dates remain RFC 3339 UTC in machine contracts. API version and Decision
File schema version are independent. Unsupported future contract versions are
rejected explicitly.

## Error handling and resilience

Writes execute transactionally. Duplicate idempotency keys with the same
request hash replay the stored response; different payloads return conflict.
Request bodies and pagination are bounded. Domain rejection is 409, invalid
input 422, absent authentication 401, insufficient permission 403, and a
tenant-hidden object 404. Unexpected errors return 500 with a correlation ID
and never a successful governance result.

## Acceptance criteria

1. Two tenants may use the same decision ID and cannot read, mutate or infer one another's data.
2. Missing tenant context, wrong role, agent approval, invalid transitions, mass-assignment fields and replay conflicts fail closed.
3. Evaluation and transition generate tenant-scoped, hash-linked audit events.
4. DE/EN errors and English fallback are automated tests.
5. API contract, repository integration and complete DRAFT-to-APPROVED/BLOCKED journeys pass without external services or LLMs.
6. CI runs lint, type, unit, integration, isolation, localization, E2E, build and available security checks.

