# ADR-004: Controlled production-pilot foundation

**Status:** Accepted for implementation — 2026-07-30

## Context

Decision Assurance v0.4 provides deterministic governance, controlled Intake and provider-neutral
Web Research in one Python distribution. Its reference deployment deliberately uses static tokens,
SQLite and synchronous provider calls. Those choices are appropriate for deterministic local tests,
but do not provide the isolation, identity assurance, recovery or operational evidence required for
a controlled production pilot.

The first pilot is governed Sales Quote Review. Human approval remains mandatory. Agents may
prepare, extract, research, validate and recommend, but cannot perform final approval. Web Research
may attach only `UNVERIFIED`, `OUTDATED` or `CONFLICTING` evidence to a tenant-matching `DRAFT`
Decision File. Only the existing Engine may produce assurance findings and outcomes.

## Considered alternatives

### A. Extend the SQLite runtime

This has the smallest initial diff and preserves the current repository implementations. It cannot
provide PostgreSQL Row-Level Security, production database roles, robust multi-process job leasing,
or realistic backup and restore evidence. Application-only tenant filters would remain the sole
isolation control. This does not meet the pilot gate.

### B. Replace persistence with a general ORM and external queue

An ORM could normalize SQL dialects and a dedicated broker could provide mature job delivery. It
would introduce a broad rewrite across Decision, Intake and Research, plus additional operational
infrastructure before the pilot needs it. ORM abstractions also do not remove the need to design and
test explicit PostgreSQL RLS policies. This creates unnecessary migration and trust-boundary risk.

### C. Provider-neutral ports with PostgreSQL-native production adapters

Keep SQLite adapters for reference/test mode. Add explicit repository, identity, job, secret,
observability, egress and recovery ports. Implement production persistence with PostgreSQL-native
transactions, migrations, roles and RLS. Store jobs in PostgreSQL and run API and Worker as separate
processes inside the same modular monolith. This preserves existing domains while providing the
required production controls without a broker or new service boundary.

## Decision

Choose alternative C.

The Python distribution remains a modular monolith with separate API and Worker entry points. Domain
contracts remain framework- and provider-neutral. PostgreSQL is mandatory in staging and production;
SQLite remains available only in explicit development and test profiles. Production startup fails
closed when PostgreSQL, OIDC, external-secret integration or other critical configuration is absent.

PostgreSQL sessions set a transaction-local tenant context. RLS policies enforce tenant equality on
all tenant-owned tables and use `FORCE ROW LEVEL SECURITY`. Application connections use a dedicated
non-owner role without `BYPASSRLS`; migration, application, read-only operations and audit/export use
separate roles. Composite keys continue to include `tenant_id`.

OIDC validation is implemented behind the identity-provider port. It validates issuer, signature,
audience, expiry, not-before, an explicit `RS256`/`ES256` algorithm allowlist and bounded clock skew.
JWKS is cached with controlled refresh for key rotation. Tenant, actor, role and actor kind are created
only from validated claims. Static tokens are rejected outside explicit development/test profiles.
Privileged transitions require `HUMAN`; agent identities never receive final approval permission.

Research provider work moves to a PostgreSQL-backed job table. API requests persist the run and one
idempotent job, then return a controlled asynchronous status. Workers claim with `FOR UPDATE SKIP
LOCKED`, lease tokens and expiry; retries are bounded with deterministic exponential backoff. Lease
recovery, cancellation, budget reservation, audit and evidence handoff are transactional and
tenant-scoped. Provider errors remain outside the Engine.

Secrets are referenced by name through a secret-provider port. Environment values are a development
adapter; production uses an external-provider abstraction. Values use redacted wrappers and must not
enter logs, audit, metrics, fingerprints, responses or artifacts. Rotation happens by resolving the
reference again, without code changes.

Egress decisions remain provider-neutral and preserve the v0.4 URL controls. Production deployment
adds network-level allow rules, bounded redirects with post-redirect validation, response-body limits,
per-tenant quotas/concurrency and provider circuit breakers. DNS rebinding between validation and
remote retrieval remains a documented provider/network residual risk.

Structured logs, metrics and health reports carry correlation identifiers and stable codes, never
raw business content or credentials. Metrics must not use tenant identifiers, URLs, decision IDs,
queries or evidence text as labels. Readiness includes database, migration, worker and required
provider/configuration checks.

Backups are encrypted PostgreSQL backups with integrity metadata and a documented point-in-time
recovery model. Restore tests must prove schema migration, audit-chain integrity, tenant isolation and
safe recovery of incomplete jobs. API and Worker containers are non-root, provider-neutral and built
from the same traceable source revision.

A machine-readable release report aggregates gates as `PASS`, `REVIEW` or `BLOCK`. This is release
governance metadata, not a Research outcome. Tenant isolation, migration, restore, audit integrity,
development authentication in production, agent approval, secret leakage, critical vulnerabilities
or Research-created assurance outcomes force `BLOCK`.

## Trust and tenant boundaries

1. HTTP input is untrusted until strict request validation.
2. Bearer tokens and claims are untrusted until OIDC verification completes.
3. Tenant context originates only in the verified identity and is re-established per transaction.
4. Background jobs are untrusted deliveries and must be leased, tenant-scoped and idempotent.
5. Provider responses and web content remain untrusted through evidence handoff.
6. The compiler can attach conservative evidence; only the Engine evaluates it.
7. Final approval is a privileged human action and is independently audited.
8. Database administrators, migration artifacts, backups and release artifacts are privileged supply
   chain boundaries and require integrity controls.

## Consequences

- PostgreSQL becomes a required test and deployment dependency for production paths.
- `psycopg` and a maintained JWT implementation become runtime dependencies; dependency bounds and
  vulnerability scanning are mandatory.
- SQL migrations remain explicit so RLS, roles and grants are reviewable.
- API and Worker can scale independently without splitting domain ownership into microservices.
- Development retains deterministic SQLite/fake-provider workflows.
- Operations must own OIDC registration, database roles, secret storage, egress rules, backups,
  retention and pilot stop decisions.
- The release can be `PASS` only with evidence from all mandatory gates.

## Explicit limitations

v0.5 targets one controlled pilot, not general production readiness. It does not add unrestricted
crawling, browser/login automation, autonomous approval, a general workflow designer, Kubernetes,
multi-region active-active operation, certification or recognized-standard claims.
