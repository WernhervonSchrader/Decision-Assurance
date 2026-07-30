# Decision Assurance Public Draft v0.5 — Production Foundation

**Status:** implementation specification approved by project owner

> Decision Assurance v0.5 is a controlled production-pilot foundation. It is not a recognized
> standard, certification or general production-readiness claim.

## A. Context assessment

The verified baseline is commit `461b8b00d816050bd1367dd5d85739f9c891dca1`, package `0.4.0`,
on a clean `main`. The isolated baseline produced 249 passing tests; Ruff format, Ruff lint, strict
Mypy and Bandit passed. Existing GitHub CI also includes pip-audit, build, OpenAPI drift, benchmarks
and Gitleaks.

The codebase is a modular Python distribution. Decision, Intake and Research already have explicit
contracts and tenant-aware SQLite repositories. Authentication is a static token mapping, provider
calls execute synchronously inside the API request, and health checks only database reachability.
These are reference-mode constraints, not production controls.

The target user is a human participant in a governed Sales Quote Review pilot. Agents may prepare,
extract, research and recommend. A human must perform material review and final approval/block.
Web Research is optional evidence support and remains unable to create an assurance outcome.

Primary constraints are preserving deterministic Engine behavior, v0.4 compatibility, tenant
isolation, German/English errors, no provider calls in default tests, provider-neutral deployment and
evidence-backed release gates. The highest risks are RLS bypass, OIDC claim manipulation, duplicate
job delivery/cost, secret leakage, restore corruption and accidental development fallback.

## B. Requirements matrix

Evidence is marked `planned` until the named test/gate has run on the implementation. A requirement
cannot be marked complete by documentation alone.

| ID | Requirement | Implementation location | Verification | Completion evidence |
| --- | --- | --- | --- | --- |
| ARCH-01 | Preserve Engine, Intake, Research, IAM, persistence and operations boundaries | `production/`, existing domains, ADR-004 | architecture dependency tests; forbidden-outcome scan | `architecture-boundaries` gate |
| GOV-01 | Only Engine creates assurance outcomes; Research never emits `PASS/REVIEW/BLOCK/APPROVED` | Research contracts/compiler; release gate | unit, metamorphic and repository scan | `research-outcome-boundary` gate |
| GOV-02 | Human identity required for final approval; agents denied | `identity.py`, `authorization.py`, transitions/API | authorization and pilot E2E negative cases | `human-approval` gate |
| DB-01 | SQLite reference mode and PostgreSQL production mode behind explicit ports | `repositories/`, `production/ports.py`, runtime factory | contract tests for both adapters | `persistence-contract` gate |
| DB-02 | PostgreSQL migrations cover Decision, Intake, Research, jobs, budgets and handoffs | `migrations/postgresql/`, packaged copies | fresh/upgrade/repeat/rollback tests | `postgres-migrations` gate |
| DB-03 | Every business table and relationship remains tenant-scoped | PostgreSQL DDL and repository SQL | schema inspection and two-tenant integration tests | `tenant-schema` gate |
| DB-04 | Forced RLS denies cross-tenant read, update, inference, cache, audit, evidence and idempotency access | RLS migrations/session context | adversarial RLS integration suite | `tenant-isolation` gate |
| DB-05 | Separate migration, application, operations-read and audit/export roles | PostgreSQL role migration and deployment config | privilege matrix tests | `database-roles` gate |
| DB-06 | Application never uses owner/migration/BYPASSRLS role | production config/startup | negative startup and database-session tests | `least-privilege-db` gate |
| DB-07 | Idempotency, budgets, audits, handoffs and transitions are transaction-safe | PostgreSQL repositories/job adapter | race/failure-injection/integration tests | `transaction-integrity` gate |
| IAM-01 | Identity provider abstraction retains static adapter only for explicit dev/test | `identity.py`, `production/ports.py`, runtime config | profile contract/startup tests | `auth-mode` gate |
| IAM-02 | OIDC verifies issuer, signature, audience, exp, nbf, algorithm and bounded skew | `identity/oidc.py` | signed-token contract/security tests | `oidc-validation` gate |
| IAM-03 | JWKS rotation is HTTPS, bounded and fail-closed | OIDC JWKS adapter/cache | rotation, unknown-kid, outage and poisoned-key tests | `jwks-rotation` gate |
| IAM-04 | Tenant, actor, role/kind and optional organization/groups come only from validated claims | OIDC claim mapper | manipulated/missing claim tests | `identity-claims` gate |
| IAM-05 | Production rejects static, unsigned, expired, wrong-audience and unknown-issuer tokens | runtime/OIDC adapter | production E2E negative matrix | `production-auth` gate |
| I18N-01 | All new user-facing security/config/job errors support DE/EN; codes remain neutral | `i18n.py`, API errors | localization parity/fallback tests | `localization` gate |
| JOB-01 | Provider-neutral job lifecycle includes all specified states and transitions | `production/contracts.py`, `jobs/` | allowed/prohibited transition unit tests | `job-lifecycle` gate |
| JOB-02 | Research API enqueues and returns controlled async status without provider calls | Research API/orchestrator split | API integration test with call counter | `async-api` gate |
| JOB-03 | Enqueue/claim/retry/backoff/cancel/lease/dead-letter are idempotent and bounded | PostgreSQL job repository/worker | duplicate, timeout, cancellation, crash and stale-lease tests | `worker-recovery` gate |
| JOB-04 | Duplicate processing cannot duplicate budgets, evidence, audit or handoff | job worker plus transactional repositories | concurrent duplicate-delivery tests | `duplicate-delivery` gate |
| CFG-01 | Typed development/test/staging/production profiles separate secrets, policies and limits | `production/config.py` | precedence and profile tests | `configuration` gate |
| CFG-02 | Production fails closed for SQLite, static auth, placeholders or missing critical config | runtime startup validation | negative production startup tests | `production-config` gate |
| SEC-01 | Secret Provider supports environment dev adapter and external production abstraction | `production/secrets.py`, ports | adapter/rotation/outage tests | `secret-provider` gate |
| SEC-02 | Secrets never enter responses, logs, audit, metrics or artifacts | redaction/logging plus scanners | canary-secret tests, Gitleaks, artifact scan | `secret-leakage` gate |
| SEC-03 | Input/output schemas are strict and bounded | Pydantic/public schemas/API middleware | contract and negative-size tests | `api-contracts` gate |
| NET-01 | Egress policy enforces HTTPS/public IP/no credentials/ports/domains/redirect revalidation | `egress/`, provider adapters | hostile URL and redirect-chain security tests | `egress-security` gate |
| NET-02 | MIME, body, redirect and timeout limits fail closed; DNS rebinding remains documented | adapters/config/docs | transport limit tests and threat-model review | `provider-bounds` gate |
| NET-03 | Per-tenant requests/results/extractions/cost/concurrency and circuit breakers are enforced | policies, PostgreSQL counters, breaker | isolation, exhaustion and recovery tests | `provider-controls` gate |
| OBS-01 | Structured logs and correlation span HTTP, Intake, Research, jobs, handoff, Decision and audit | `observability/`, middleware/worker | trace-correlation integration test | `correlation` gate |
| OBS-02 | Metrics cover volume/errors/latency/jobs/providers/retries/budget/cache/evidence/outcomes without sensitive labels | metrics adapter/instrumentation | label allowlist and canary tests | `metrics-safety` gate |
| OBS-03 | Liveness/readiness expose database, worker, migration and provider/config readiness | health routes/probes | dependency failure tests | `health` gate |
| OBS-04 | Detect audit gaps, isolation probes, auth failures, cost anomalies, failed migrations and dead letters | detectors/metrics/runbooks | synthetic event tests | `operational-detection` gate |
| DR-01 | RTO/RPO, encrypted backup, retention and ownership are explicit | `docs/BACKUP-RESTORE.md`, scripts | documentation contract test | `recovery-policy` gate |
| DR-02 | Backup/restore/integrity/PITR concept is executable and tenant-safe | `scripts/postgres/`, Compose test | restore smoke, audit and RLS tests | `backup-restore` gate |
| DEP-01 | Non-root API/Worker images with health checks and traceable build metadata | Dockerfiles/entry points | container smoke and metadata tests | `container-build` gate |
| DEP-02 | Provider-neutral Compose staging stack starts reproducibly with explicit limits | `compose.yaml`, staging docs | staging smoke test | `staging-smoke` gate |
| DEP-03 | Container scan, SBOM, immutable metadata and release checksums are generated | CI/build scripts | scanner/SBOM/checksum artifact tests | `supply-chain` gate |
| CI-01 | Existing quality, benchmarks, OpenAPI, schema, audit and secret gates remain | `.github/workflows/` | CI | `legacy-regression` gate |
| CI-02 | PostgreSQL/RLS/OIDC/worker/migration/restore/container/staging/config/health gates run | CI workflows | CI job matrix | `production-ci` gate |
| CI-03 | Machine-readable report computes `BLOCK` for every mandatory blocking condition | release verifier/schema | unit/contract and injected-failure tests | `release-verification` artifact |
| PILOT-01 | Explicit Sales Quote Review profile defines limits, providers, data, retention, escalation and stops | `config/pilot/`, public schema | profile contract tests | `pilot-profile` gate |
| PILOT-02 | Web Research evidence stays conservative and optional | Research compiler/pilot flags | pilot E2E and outcome scan | `pilot-research` gate |
| PILOT-03 | Deterministic production-like E2E covers OIDC→Intake→Research→Engine→human decision→audit→restore | `tests/production/e2e/` | PostgreSQL/fake-provider E2E | `controlled-pilot-e2e` gate |
| DATA-01 | Data minimization, allowed classes, retention, deletion/export and backup protection are defined | pilot/config/docs/repositories | policy and retention tests | `data-protection` gate |

## C. Proposed architecture

### Components and data flow

The deployment is one modular distribution with `decision-assurance-api` and
`decision-assurance-worker` processes. PostgreSQL stores all business records and the job queue.
Explicit ports isolate PostgreSQL, OIDC/JWKS, secrets, egress, logs, metrics and backup providers.
SQLite, static tokens, fake providers and in-memory observability remain deterministic reference
adapters under development/test profiles only.

The request flow is:

```text
Bearer token -> OIDC verification -> Identity/TenantContext -> authorization
-> tenant-local PostgreSQL transaction/RLS -> domain operation -> atomic audit/idempotency
```

The Research flow is:

```text
validated create request -> Research Run + QUEUED job (one transaction) -> HTTP 202
-> Worker lease -> budget/concurrency reservation -> Brave discovery -> egress/source selection
-> Firecrawl extraction -> normalization/evidence policy -> conservative DRAFT handoff
-> job/run/audit completion (transactional)
```

The governance flow remains:

```text
Intake interprets untrusted input -> compiler creates outcome-free Decision File
-> optional Research attaches conservative evidence -> Engine evaluates deterministically
-> human reviewer -> human approver or blocker
```

### Tenant boundary

OIDC creates `TenantContext`; client tenant fields remain forbidden. API and Worker establish a
transaction-local tenant setting before repository access. Forced RLS and composite constraints deny
cross-tenant relationships. Operational roles do not silently impersonate tenants. Explicit
audit/export workflows are separately authorized and audited.

### Localization flow

Machine enums, schema fields, audit types and reason codes remain English-neutral identifiers.
`Accept-Language` chooses German or English user-facing errors with English fallback. Query locale,
content language, provider language and tenant default locale remain distinct fields.

### Error and recovery flow

Input/auth failures return generic localized errors with correlation IDs. Production startup and
readiness fail for missing critical dependencies. Provider failures change only Research/job state;
they cannot change Engine policy or confidence. Retry schedules are bounded. Worker lease expiry
supports crash recovery. Database/migration/restore/audit failures block release and invoke explicit
rollback/runbook procedures.

## D. Threat model

| Threat | Likelihood / impact | Prevention | Detection | Response and residual risk |
| --- | --- | --- | --- | --- |
| OIDC claim manipulation | medium / critical | signature, issuer/audience/time checks; strict mappings | auth failure metrics and correlated logs | revoke token/client; compromised issuer remains critical |
| Token replay | medium / high | short expiry, TLS, audience, optional upstream `jti` controls | repeated subject/token-pattern alerts without token logging | revoke sessions; bearer theft window remains |
| Compromised JWKS source/key rotation | low / critical | HTTPS issuer allowlist, bounded cache/refresh, algorithm allowlist | unknown key/refresh anomaly alerts | stop readiness/revoke issuer; trusted IdP compromise remains |
| Agent impersonates human | medium / critical | validated actor kind; human-only privileged permissions | denied approval attempts and audit | disable identity mapping; compromised human account remains |
| Cross-tenant IDOR/inference | medium / critical | identity tenant, forced RLS, composite keys, non-enumerating errors | RLS/authorization denial metrics | pilot stop and incident response; DB superuser remains privileged |
| Database role escalation/RLS bypass | low / critical | non-owner app role, no `BYPASSRLS`, separate credentials | role/grant verification gate | rotate credentials/revoke role; privileged DBA risk remains |
| Queue poisoning | medium / high | strict job schema/hash, tenant context, authenticated worker | invalid-job/dead-letter metrics | quarantine/dead-letter; privileged DB writer remains a risk |
| Duplicate delivery | high / high | deterministic IDs, leases, conditional transitions, atomic budgets/handoffs | duplicate-claim/cost invariants | converge/recover; external provider side effects remain bounded |
| Worker impersonation/stale lease | medium / high | worker credentials, hashed lease tokens, expiry and compare-and-set | lease conflict/recovery metrics | revoke worker and recover jobs |
| Provider cost exhaustion | high / high | per-tenant budget/concurrency/rate limits and circuit breakers | budget/cost anomaly metrics | suspend Research/tenant, retain Engine operation |
| SSRF/DNS rebinding/redirect abuse | medium / critical | public HTTPS policy, network egress, redirect revalidation, port/domain limits | denied-target and redirect metrics | block provider/domain; provider-side DNS timing remains residual |
| Poisoned provider content | high / high | normalization, prompt-injection risks, no tool/policy authority, conservative status | evidence risk metrics/audit | human review or discard; semantic detection is incomplete |
| Secret manager outage/leak | medium / critical | named references, redacted types, no production env fallback | readiness and canary-secret scans | fail closed, rotate, incident runbook |
| Observability leakage | medium / high | structured allowlists, redaction, low-cardinality labels | canary-secret and label tests | purge/rotate/restrict; operator backend remains trusted |
| Backup exposure/poisoned restore | low / critical | encryption, integrity metadata, access separation, restore validation | backup verification and audit-chain gate | quarantine backup/use prior point; key custodian risk remains |
| Failed/tampered migration | medium / critical | checksum/version ledger, transactional DDL, separate role | migration and schema-drift gates | rollback application/schema according to compatibility plan |
| Deployment artifact tampering | low / critical | checksums, SBOM, image scan, immutable metadata | CI provenance/checksum verification | block release/rebuild from trusted commit |
| Audit tampering/gaps | low / critical | transactionally persisted hash chain and verification | periodic/restore audit verifier | release block, incident response; privileged DB compromise residual |
| Denial of service | high / medium | bounded inputs, quotas, timeouts, resource limits and backpressure | latency/error/backlog metrics | shed load/disable optional Research; distributed attacks external |

## E. Implementation constraints

- No implementation may weaken v0.4 tenant or governance controls.
- No live Brave or Firecrawl calls run by default.
- PostgreSQL tests use isolated databases and deterministic seed data.
- OIDC tests use locally generated test keys/JWKS, never an external issuer.
- The PostgreSQL job table is preferred over a new broker for v0.5.
- Production migrations run out-of-band with the migration role.
- Production application startup checks schema compatibility but does not auto-migrate.
- Container and staging tests may be skipped locally only when the required engine is unavailable;
  CI release gates may not silently skip them.
- Historical v0.1–v0.4 schemas/docs remain for compatibility and are explicitly exempt from the
  mixed-version prohibition.

## F. Acceptance criteria

1. Existing 249 tests and both benchmarks remain green.
2. PostgreSQL fresh, v0.4 upgrade, repeat and rollback tests pass.
3. Forced-RLS isolation tests deny cross-tenant read, update and inference for every domain.
4. Production application sessions use the application role without owner/migration/BYPASSRLS.
5. OIDC positive, key-rotation and all mandatory negative tests pass.
6. Static authentication and SQLite are rejected by production profile startup.
7. Research create returns asynchronously and default tests make no live provider calls.
8. Crash, duplicate delivery, cancellation, budget exhaustion and stale lease recovery converge
   without duplicate cost, evidence, handoff or audit.
9. Agent identities cannot review/approve where human authority is mandatory.
10. Secret canaries are absent from API, logs, audits, metrics, SBOM and artifacts.
11. Health/readiness accurately fail on critical dependency, schema, worker and configuration faults.
12. Backup/restore smoke proves audit integrity, tenant isolation and safe job recovery.
13. API and Worker images run non-root and expose traceable immutable build metadata.
14. CI builds/scans images, emits SBOM/checksums and produces a machine-readable release report.
15. The controlled Sales Quote Review E2E passes deterministically in DE/EN with two tenants and
    proves complete correlation/audit plus human final authority.
16. No mandatory gate is skipped; final release status is `PASS` only when every gate passes.
