# Production Foundation Architecture v0.5

Decision Assurance v0.5 is a controlled production-pilot foundation. It is not a recognized
standard, certification or general production-readiness claim.

## Runtime shape

```text
OIDC issuer/JWKS
       |
       v
API process -> authenticated Identity -> tenant-scoped PostgreSQL transaction
       |                                  | Decision / Intake / Research tables
       | enqueue                          | RLS + audit + idempotency + budgets
       v                                  |
PostgreSQL job table <---- lease ---- Worker process
                                      | Brave discovery port
                                      | Egress policy
                                      | Firecrawl extraction port
                                      v
                              conservative evidence handoff
                                      |
                                      v
                             Decision Assurance Engine
                                      |
                                      v
                           human review and approval/block
```

API and Worker are separate processes built from one modular Python distribution. PostgreSQL is the
coordination and production persistence boundary. No provider is called from the synchronous API
request. SQLite and static identities are reference adapters enabled only by explicit development or
test profiles.

## Component ownership

| Component | Owns | Must not own |
| --- | --- | --- |
| Decision Engine | deterministic findings and assurance outcomes | identity, provider access, job delivery |
| Controlled Intake | untrusted input interpretation and verified/confirmed facts | assurance outcomes, final approval |
| Web Research | discovery, guarded extraction, evidence assessment | `PASS`, `REVIEW`, `BLOCK`, `APPROVED` |
| Identity and Access | token verification, identity mapping, authorization | tenant values from request payloads |
| Persistence | tenant transactions, RLS, atomic state/audit/idempotency | domain policy decisions |
| Operational Infrastructure | jobs, secrets, logging, metrics, health, backup and deployment | governance outcomes |

## Authentication and authorization flow

1. The API accepts a bearer token and a correlation identifier.
2. The OIDC adapter selects only configured issuers and allowed algorithms.
3. Signature, audience, `exp`, `nbf` and bounded skew are verified against JWKS.
4. Validated claims map to actor ID, tenant, role, actor kind and optional organization/groups.
5. Central authorization checks the operation and object-level tenant boundary.
6. Approval additionally requires a `HUMAN` identity; an agent role mapping fails closed.
7. Stable machine reason codes are localized at the API boundary in German or English.

## Persistence and tenant flow

Each request or job opens a short transaction and sets a transaction-local tenant identifier.
PostgreSQL RLS compares that value with the row `tenant_id`. Tenant-owned primary, foreign and unique
keys include the tenant. Missing context yields no rows and denied writes. Application code uses the
application role, not owner or migration credentials. Read-only and audit/export access are separate,
explicitly granted operational paths.

SQLite adapters continue to include tenant predicates and composite keys, but cannot satisfy the
production profile because SQLite has no RLS.

## Asynchronous research flow

1. A validated request creates or reuses a tenant-bound Research Run.
2. The same transaction creates one deterministic job and an audit event.
3. The API returns `202` with stable run/job references.
4. A Worker claims an available job with a lease and a worker identity.
5. Before each provider call it reserves budget atomically and checks tenant quotas, circuit state and
   egress policy.
6. Successful attempts, partial failures and retry scheduling persist with audit in one transaction.
7. A stale lease becomes claimable after recovery; duplicate delivery cannot duplicate cost,
   evidence, audit or handoff.
8. Eligible evidence attaches only to an unchanged tenant-matching `DRAFT` Decision File as
   `UNVERIFIED`, `OUTDATED` or `CONFLICTING`.

## Secrets and configuration flow

The runtime loads a typed environment profile. Non-secret settings name secret references. A
Secret Provider resolves values at startup or controlled refresh. Production rejects environment-only
credentials, placeholders, static identities, SQLite, incomplete OIDC and missing critical limits.
Secret values are redacted by type and excluded from logs, errors, audit, metrics and build metadata.

## Observability and audit flow

Correlation IDs connect request, Intake, Research, job, provider attempt, handoff, Decision File and
audit event. Structured logs carry stable event types and low-cardinality operational fields. Metrics
exclude tenant/business identifiers. Audit events remain domain records with actor, tenant, state,
reason and hash-chain information. Operational detection covers audit gaps, authorization probes,
cross-tenant attempts, cost anomalies, failed migrations and dead-letter jobs.

## Failure behavior

- Invalid or unavailable identity: localized `401`, no claim detail.
- Forbidden role, actor kind or tenant: localized `403` or non-enumerating `404`.
- Missing production dependency/configuration: startup/readiness failure.
- Provider outage: bounded retry or partial/failed job; Engine confidence is unchanged.
- Worker crash: lease expiry and controlled recovery.
- Database outage: readiness fails and no fallback persistence is selected.
- Secret-provider outage: fail closed for required secrets and alert operations.
- Migration/restore/audit failure: release `BLOCK` and follow the rollback/runbook path.

## External dependencies

- PostgreSQL with RLS and point-in-time recovery capability.
- An OIDC issuer with HTTPS JWKS and key rotation.
- An external secret provider selected by deployment.
- Brave Search and Firecrawl only when the pilot feature and tenant policy permit them.
- A container runtime and CI scanners for build, SBOM, vulnerability and secret verification.
