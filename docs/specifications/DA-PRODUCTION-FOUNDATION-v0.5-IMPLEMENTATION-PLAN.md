# Decision Assurance v0.5 — Production Foundation Implementation Plan

This plan implements ADR-004 and the approved v0.5 specification. Each stage starts with failing
tests, ends with focused and full verification, and is committed independently. A Draft PR is opened
after Stage 1 and remains draft until every blocking gate passes.

## Baseline evidence

- Branch point: `461b8b00d816050bd1367dd5d85739f9c891dca1`
- Baseline: 249 tests passed with one existing Starlette/httpx deprecation warning.
- Ruff format/lint, strict Mypy and Bandit passed.
- GitHub CLI 2.96.0 is authenticated for `WernhervonSchrader`.
- Feature branch: `feature/production-foundation-v0.5`.

## Stage 1 — Architecture and contracts

### Files

- `docs/adr/ADR-004-production-foundation.md`
- `docs/PRODUCTION-ARCHITECTURE.md`
- `docs/specifications/DA-PRODUCTION-FOUNDATION-v0.5.md`
- this plan
- `src/decision_assurance/production/contracts.py`
- `src/decision_assurance/production/ports.py`
- `schemas/production/*.schema.json` and packaged byte-identical copies
- `tests/production/unit/test_contracts.py`
- `tests/production/contract/test_production_schemas.py`

### Contracts

- `IdentityProviderPort.authenticate(token) -> Identity`
- `PersistenceReadinessPort`, `MigrationPort`
- `JobRepositoryPort.enqueue/claim/heartbeat/complete/fail/cancel/recover_stale`
- `SecretProviderPort.resolve(reference) -> SecretValue`
- `EgressPolicyPort.validate(tenant, url) -> canonical URL`
- `StructuredLoggerPort`, `MetricsPort`, `HealthProbePort`, `BackupProviderPort`
- job, health, build, release gate and pilot profile value objects

### Tests and expected result

Contracts reject unsafe OIDC algorithms, incomplete leases, non-human pilot approval, invalid limits
and unreasoned non-pass gates. Public and packaged JSON Schemas are byte-identical and reject unknown
fields. Existing suites remain unchanged.

### Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\production\unit tests\production\contract -q
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m mypy src
```

Commit: `Specify production foundation contracts`. Push and open Draft PR targeting `main`.

## Stage 2 — PostgreSQL persistence and RLS

### Files

- `src/decision_assurance/repositories/postgresql.py`
- `src/decision_assurance/intake/postgresql_repository.py`
- `src/decision_assurance/web_research/postgresql_repository.py`
- `src/decision_assurance/jobs/postgresql.py`
- `src/decision_assurance/persistence/factory.py`
- `src/decision_assurance/persistence/postgresql.py`
- `migrations/postgresql/001_v0_4_baseline.sql`
- `migrations/postgresql/002_production_foundation_v0_5.sql`
- `migrations/postgresql/roles.sql`
- packaged migration copies
- `tests/production/postgresql/`

### Design

Use `psycopg` v3 and explicit SQL, not an ORM rewrite. A connection factory begins a transaction,
executes `SET LOCAL decision_assurance.tenant_id = %s`, and never exposes an unscoped application
session. RLS policies compare `tenant_id` to `current_setting(..., true)` and are forced. The
application role has DML/sequence rights only; migrations are out-of-band. Conditional updates,
unique constraints, `ON CONFLICT`, `FOR UPDATE` and compare-and-swap make idempotency, budgets,
audit, lifecycle and handoffs atomic.

### Test-first cases

1. Fresh schema and role installation.
2. Import/upgrade from v0.4-compatible data.
3. Repeated migration with unchanged checksum.
4. Deliberate failed migration rolls back.
5. Tenant A cannot select/update/delete Tenant B for Decision, Intake, Research, jobs, cache,
   audit, evidence, budgets or idempotency.
6. Wrong/missing tenant context returns indistinguishable absence or permission denial.
7. Application role is non-owner and has no `BYPASSRLS`.
8. Concurrent budget reservations cannot exceed the limit.
9. Concurrent transitions and handoffs have one winner and converge on replay.

PostgreSQL tests use a unique test database/schema, two tenants and explicit cleanup. CI supplies a
PostgreSQL service; no production database is used.

### Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\production\postgresql -q
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all database and existing SQLite tests pass. Commit:
`Add PostgreSQL persistence and tenant RLS`.

## Stage 3 — OIDC identity and authorization

### Files

- `src/decision_assurance/identity.py` (roles/actor constraints without breaking v0.4 mappings)
- `src/decision_assurance/identity/oidc.py` or a non-conflicting identity package chosen during refactor
- `src/decision_assurance/identity/jwks.py`
- `src/decision_assurance/authorization.py`
- `src/decision_assurance/api/dependencies.py`
- `tests/production/identity/`
- `docs/IDENTITY.md`

### Design

Use a maintained JWT library. Configure exact issuers/audiences and `RS256`/`ES256`. Cache JWKS by
issuer with bounded TTL and refresh once for an unknown `kid`. Validate signature and registered
claims before mapping tenant/actor/role/kind. Add Reviewer and System Administrator only with an
explicit least-privilege matrix. Approval requires both permission and `ActorKind.HUMAN`; agents and
services fail closed. Static tokens are constructed only by development/test runtime profiles.

### Test-first cases

Valid token, rotation, expired, future `nbf`, excessive skew, wrong audience, wrong issuer, unsigned,
algorithm confusion, unknown key, malformed claims, missing tenant, invalid role/kind, manipulated
payload, static token in production, and DE/EN generic errors. Tests use local ephemeral keys and
MockTransport JWKS; there is no live identity provider.

Commit: `Add production OIDC authentication`.

## Stage 4 — Asynchronous Research worker and jobs

### Files

- `src/decision_assurance/jobs/contracts.py`, `lifecycle.py`, `repository.py`, `worker.py`
- `src/decision_assurance/web_research/service.py`
- `src/decision_assurance/api/routes/research.py`
- `src/decision_assurance/api/worker_runtime.py`
- `tests/production/jobs/`, `tests/production/worker/`

### Design

Creating Research persists the run, `QUEUED` job, audit and idempotency response in one transaction
and returns `202`. Worker claims with `FOR UPDATE SKIP LOCKED`, random lease token (stored hashed),
expiry and conditional ownership. Backoff is `min(maximum, base * 2^(attempt-1))` without hidden
sleep in tests. A poison/non-retryable response fails or dead-letters; retryable failures schedule
`RETRY_WAIT`. Logical cancellation prevents new provider calls. Recovery requeues expired leases.
Every provider call first obtains an atomic tenant budget/concurrency reservation.

### Test-first cases

API call counter remains zero; job lifecycle positive/negative transitions; duplicate enqueue and
delivery; worker crash; stale lease; invalid lease; timeout; exponential retry; maximum attempts;
cancellation before/while running; budget and concurrency exhaustion; partial source failure;
poisoned content; replay after handoff; no duplicate cost/evidence/audit.

Commit: `Add asynchronous research worker`.

## Stage 5 — Secrets and production configuration

### Files

- `src/decision_assurance/production/config.py`
- `src/decision_assurance/production/secrets.py`
- `src/decision_assurance/api/runtime.py`
- `src/decision_assurance/api/worker_runtime.py`
- `.env.example`, `config/production.example.json`, `config/pilot/sales-quote-review.json`
- `tests/production/configuration/`, `tests/production/security/test_secret_leakage.py`

### Design

Typed profiles select database/auth/secret/worker/observability adapters. Non-secret configuration
contains only secret reference names. The environment secret adapter is allowed in development/test;
an external-provider port is mandatory in staging/production. Production rejects SQLite, static auth,
empty/placeholder secrets, incomplete OIDC, unsafe bounds and fallback adapter selection. Secret
values are explicitly resolved and redacted; rotation invalidates controlled caches.

### Tests

Missing/malformed/placeholder secrets, precedence, reference rotation, provider outage, production
fallback prevention and canary absence from repr/log/API/audit/metrics/artifacts. Commit:
`Add production secrets and configuration`.

## Stage 6 — Observability and operational health

### Files

- `src/decision_assurance/observability/logging.py`, `metrics.py`, `health.py`, `detection.py`
- API middleware, Intake/Research/job/handoff instrumentation
- `docs/OBSERVABILITY.md`, `docs/OPERATIONS.md`, `docs/INCIDENT-RESPONSE.md`
- `tests/production/observability/`

### Design and tests

JSON logs use an allowlist and redactor. Correlation IDs propagate across every material record and
process boundary. Metrics use bounded label enums only. Liveness is process-local; readiness checks
database/schema, worker heartbeat and required configuration/provider enablement. Synthetic tests
prove each dependency failure, cross-boundary correlation, label rejection, secret/content redaction,
audit-gap and anomaly detection.

Runbooks cover provider/database outage, secret compromise, migration failure, worker backlog,
tenant-isolation suspicion, audit corruption and rollback. Commit:
`Add observability and operational health`.

## Stage 7 — Deployment, backup and recovery

### Files

- `Dockerfile.api`, `Dockerfile.worker`, `.dockerignore`, `compose.yaml`
- `scripts/postgres/backup.ps1`, `restore.ps1`, `verify_restore.py`
- `docs/DEPLOYMENT.md`, `docs/DATABASE.md`, `docs/BACKUP-RESTORE.md`
- `tests/production/container/`, `tests/production/recovery/`

### Design

One multi-stage minimal Python base produces non-root API and Worker images with read-only compatible
paths, health checks and build metadata. Compose provides PostgreSQL, API and Worker with explicit
resources and secrets by reference for local staging. Backup uses PostgreSQL-native encrypted-storage
compatible output, checksums and metadata. Restore targets a fresh instance, then runs compatibility,
audit, RLS and job-recovery verification. RTO/RPO and PITR responsibilities are explicit.

### Tests

Image build/non-root/metadata/health; Compose smoke; full backup/restore; deliberate corrupt backup;
migration after restore; audit-chain/RLS after restore; stale jobs recovered exactly once. Commit:
`Add deployment and recovery foundation`.

## Stage 8 — CI/CD and release governance

### Files

- `.github/workflows/ci.yml`, optional focused reusable workflows
- `src/decision_assurance/release_verification.py`
- `scripts/release/generate_report.py`, `checksums.py`
- `schemas/production/release-verification.schema.json`
- `tests/production/release/`
- CI verification documentation

### Design and gates

Retain all existing checks and add PostgreSQL/RLS, OIDC, worker, migrations, restore, containers,
health and production startup. Generate CycloneDX/SPDX-compatible SBOM, scan images, and checksum
artifacts. The report validates evidence and computes the most severe status. These conditions always
force `BLOCK`: tenant isolation, critical vulnerability, migration/restore/audit failure, static auth
in production, Research outcome, agent approval or secret leakage.

Injected-failure tests prove that no artifact publication step is eligible after a blocking gate.
Commit: `Add production release gates`.

## Stage 9 — Controlled Sales Quote Review pilot E2E

### Files

- `config/pilot/sales-quote-review.json`
- `tests/production/e2e/test_sales_quote_pilot.py`
- deterministic fixtures under `tests/production/fixtures/`
- `docs/PILOT.md`, `docs/PRODUCTION-READINESS.md`
- README, changelog, architecture/security/tenancy/localization/testing updates
- OpenAPI v0.5 and public/packaged schemas

### E2E environment and coverage

- Framework: Pytest + FastAPI client + real isolated PostgreSQL + API/Worker service objects.
- Seed: two tenants, human Generator/Validator/Reviewer/Approver, Tenant Admin and denied Agent.
- Identity: deterministic local OIDC issuer keys/JWKS; no static production token.
- Providers: Fake Brave and Fake Firecrawl with deterministic clock/IDs; no live network.
- Journey: OIDC tenant resolution, quote Intake, extraction, human confirmation, compilation,
  optional background Research, evidence handoff, Engine evaluation, human review, human approval or
  block, complete audit/correlation/metrics, backup, restore and post-restore isolation.
- Locale: German interface/quote and English source plus explicit fallback tests.
- Browser/device: API-only pilot has no browser UI; HTTP contract coverage replaces browser matrix.
- CI: one isolated service stack per run; unique database; no retries that hide failure.
- Artifacts: sanitized JUnit, release report, migration/restore report, logs and traces on failure;
  no raw input/provider response or secrets.
- Flakiness controls: fixed clock, seeded identifiers, fake providers, bounded polling and explicit
  worker-drain condition.

Commit: `Add controlled pilot end-to-end verification`, followed by
`Document and verify Decision Assurance v0.5` for version/OpenAPI/final evidence.

## Full verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m bandit -q -r src -s B105
.\.venv\Scripts\python.exe -m pip_audit
.\.venv\Scripts\python.exe -m build
decision-assurance benchmark tests\gold\manifest.json
.\.venv\Scripts\python.exe -m pytest tests\intake\benchmark -q
decision-assurance-openapi <temporary-v0.5-file>
git diff --check origin/main...HEAD
git status
```

CI additionally requires PostgreSQL, container scan, SBOM, restore and staging smoke evidence. No
mandatory unavailable tool is treated as a pass. Final report status is computed, not asserted.

## Rollback boundaries

- Application rollback uses the prior immutable image and compatible schema window.
- Additive migrations are preferred; destructive cleanup is deferred beyond rollback windows.
- A failed migration rolls back its transaction and leaves the previous schema ledger entry intact.
- Worker rollout first pauses claims, drains/returns leases and keeps jobs compatible with N-1.
- OIDC/secret changes retain a tested prior reference during rotation.
- Data recovery restores to a new instance, verifies integrity/RLS/audit, then switches traffic.
