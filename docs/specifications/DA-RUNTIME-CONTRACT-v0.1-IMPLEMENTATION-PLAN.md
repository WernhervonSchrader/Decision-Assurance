# Runtime Contract v0.1 — Implementation Plan

**Status:** Proposed; implementation is not authorized

**Basis:** `96b32da9e146b3b276c5fec4e636f67f6ea10889`

**ADR:** [ADR-007](../adr/ADR-007-runtime-contract-execution-evidence.md)

**Specification:** [Runtime Contract v0.1](DA-RUNTIME-CONTRACT-v0.1.md)

## Scope and constraints

After independent approval, implement the smallest standalone Runtime Contract described by ADR-007.
Do not modify Decision File v0.2 semantics, introduce general tracing, store prohibited raw content,
claim production non-bypassability, deploy or grant organizational acceptance.

Use test-driven tasks. Preserve tenant context through API, service, repositories, jobs, events,
caches and artifact resolution. Stage, commit, push and PR creation each require authorization.

## Proposed architecture

```text
Verified OIDC Identity
  -> Tenant + Authorization Policy
  -> Runtime Contract Binder
  -> Execution Authorization Gate
  -> Atomic Attempt Reservation
  -> Protected Target Port
  -> Evidence Observer / Guarded Artifact Resolver
  -> Independent Evidence Verifier
  -> Deterministic Completion Gate
  -> Tenant-scoped Append-only Execution Ledger
```

Trust boundaries are OIDC, API input, PostgreSQL/RLS, protected target adapters, external evidence
stores and audit/export consumers. Secrets and external I/O occur only after authentication, tenant,
authorization, schema, binding, required audit and egress gates.

## Commit 1 — contract and deterministic domain model

**Proposed message:** `feat(runtime-contract): add versioned execution evidence contracts`

### 1.1 Write failing contract and policy tests

Exact paths:

- `tests/runtime_contract/contract/test_runtime_schemas.py`
- `tests/runtime_contract/unit/test_canonicalization.py`
- `tests/runtime_contract/unit/test_completion_policy.py`
- `tests/fixtures/runtime-contract/`

Cover valid contracts, unknown fields/version/algorithm, every binding mutation, missing/stale/
unavailable evidence, circular provenance, replay IDs and deterministic key ordering. Assert codes,
not localized prose.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\runtime_contract\contract tests\runtime_contract\unit -q
```

Expected red phase: missing schemas/modules. Expected green phase: zero failures and stable fixtures.

### 1.2 Add schemas and package resources

- `schemas/runtime/runtime-contract.schema.json`
- `schemas/runtime/execution-event.schema.json`
- `schemas/runtime/execution-evidence.schema.json`
- mirrors under `src/decision_assurance/schemas/runtime/`
- `src/decision_assurance/validation.py` only to register the contract family

Use Draft 2020-12, `additionalProperties: false`, exact versions, bounded values and no unrestricted
payload fields. Test installed resources and byte-equality of mirrors.

### 1.3 Add pure domain policies

- `src/decision_assurance/runtime_contract/__init__.py`
- `src/decision_assurance/runtime_contract/models.py`
- `src/decision_assurance/runtime_contract/canonicalization.py`
- `src/decision_assurance/runtime_contract/policy.py`
- `src/decision_assurance/runtime_contract/errors.py`

Define typed immutable models, versioned canonicalization, binding checks, independence policy and a
pure completion function. No network, database or framework dependency enters policy code.

Commit gate: focused tests, schema mirrors, Ruff, Mypy and `git diff --check` pass; Decision File v0.2
schema hash equals the approved base.

## Commit 2 — tenant-bound ledger and orchestration

**Proposed message:** `feat(runtime-contract): enforce evidence-gated execution completion`

### 2.1 Write failing persistence/concurrency tests

- `tests/runtime_contract/integration/test_sqlite_runtime_repository.py`
- `tests/runtime_contract/postgresql/test_runtime_migration.py`
- `tests/runtime_contract/postgresql/test_runtime_rls.py`
- `tests/runtime_contract/postgresql/test_runtime_concurrency.py`
- `tests/production/unit/test_postgresql_migrations.py`
- `tests/production/postgresql/test_migration_contract.py`

Test tenant keys, forced RLS, missing tenant, cross-tenant references, append-only denial, chain order,
atomic state/audit/idempotency, authorization races, duplicate completion, lease loss and rollback.
Parallel tests use at least two connections and prove one effective owner. Failure injection after a
target may have accepted the request must produce `EFFECT_UNKNOWN`, must not return success and must
prove that the orchestrator does not blindly execute the effect again.

### 2.2 Add migrations and repository ports

Provisional paths; recheck numbering against `origin/main` immediately before implementation:

- `migrations/004_runtime_contract_v0_10.sql`
- `src/decision_assurance/migrations/004_runtime_contract_v0_10.sql`
- `migrations/postgresql/005_runtime_contract_v0_10.sql`
- `src/decision_assurance/migrations/postgresql/005_runtime_contract_v0_10.sql`
- `src/decision_assurance/runtime_contract/ports.py`
- `src/decision_assurance/runtime_contract/repository.py`
- `src/decision_assurance/runtime_contract/postgresql.py`

Every key/relation includes tenant. PostgreSQL enables and forces RLS. Runtime events are append-only
for application roles. Idempotency includes tenant, actor, operation, key and request digest.

### 2.3 Add service and protected execution port

- `src/decision_assurance/runtime_contract/service.py`
- `src/decision_assurance/runtime_contract/execution.py`
- `src/decision_assurance/runtime_contract/evidence.py`
- `tests/runtime_contract/integration/test_execution_ordering.py`

Use dependency-inverted ports and deterministic fakes/spies. Prove zero target/evidence calls before
required gates. Reserve before target I/O; complete only after evidence. Bounded retries must not
repeat an uncertain target effect; reconciliation uses adapter idempotency or independent evidence.

Commit gate: SQLite/PostgreSQL integration, migration parity, cross-tenant/concurrency negatives and
secret-canary checks pass.

## Commit 3 — API, identity, localization and E2E

**Proposed message:** `test(runtime-contract): verify identity localization and end-to-end gates`

### 3.1 Add failing API/authorization tests, then routes

- `src/decision_assurance/api/schemas.py`
- `src/decision_assurance/api/routes/runtime_contracts.py`
- `src/decision_assurance/api/app.py`
- `src/decision_assurance/authorization.py`
- `tests/runtime_contract/contract/test_runtime_api.py`
- `tests/runtime_contract/security/test_runtime_authorization.py`
- `docs/openapi-v0.6.json` only if API-version review selects v0.6

Separate bind, authorize, attempt, evidence, verify and completion operations. Bodies never establish
tenant, actor, role, credential or verifier authority. Authorization precedes repository/adapter use.
Do not overwrite an existing OpenAPI version.

### 3.2 Add localization

- existing catalogs discovered at implementation time
- `tests/runtime_contract/unit/test_localization.py`
- browser/API E2E assertions

Add DE/EN labels for visible states/reasons. Test catalog completeness, explicit locale, tenant/user
fallback, localized formatting and identical normative values.

### 3.3 Add Keycloak/PostgreSQL/API/browser E2E

- `tests/runtime_contract/e2e/test_runtime_journeys.py`
- `tests/keycloak/e2e/test_keycloak_oidc.py`
- `tests/production/e2e/test_sales_quote_pilot.py`
- `ui/e2e/pilot.spec.ts`

Cover two-tenant success; wrong tenant; manipulated action/approval/constraints; authorization,
attempt/evidence replay; self-verification; stale/unreachable/tampered evidence; audit/evidence outage;
DE/EN; logout/session expiry and prohibited roles. Tests seed/clean deterministic data. Failure
traces/screenshots are scanned for credentials and PII.

Commit gate: OpenAPI drift, Keycloak, PostgreSQL, browser, authorization and tenant negatives pass.
This proves only the tested topology, not production non-bypassability.

## Commit 4 — implemented documentation and development evidence

**Proposed message:** `docs(runtime-contract): record verified implementation evidence`

Update only after behavior exists:

- `docs/DECISION_FILE_CONTRACT.md` with an unchanged-v0.2 cross-reference only
- `docs/TRANSITION_POLICY.md`
- `docs/API.md`
- `docs/ARCHITECTURE.md`
- `docs/DATABASE.md`
- `docs/IDENTITY.md`
- `docs/LOCALIZATION.md`
- `docs/SECURITY.md`
- `docs/THREAT_MODEL.md`
- `docs/TESTING.md`
- `docs/DEPLOYMENT-EVIDENCE.md`
- `docs/RETENTION-DELETE-LEGAL-HOLD.md`
- `README.md`
- commit-bound Development Evidence under the established documentation path

Describe implemented behavior only. Unavailable external gates remain `NOT TESTED` or `BLOCKED`.
Record exact revision, environment, commands, results, artifact digests and residual risks.

## Verification matrix

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe format --check .
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe src
.\.venv\Scripts\decision-assurance.exe benchmark benchmarks\dats\v0.1.0\catalog.json
git diff --check
```

| Layer | Strategy | Expected evidence | Flakiness control |
| --- | --- | --- | --- |
| PostgreSQL | existing PostgreSQL 16 marker/job, fresh schema | migration/RLS/concurrency/rollback | deterministic IDs, barriers, bounded timeouts |
| Keycloak | isolated Compose realm | PKCE/JWKS/tenant/roles/kind | ephemeral secrets and readiness wait |
| Security | Bandit, audit, Gitleaks, negative tests | no unresolved critical or canary | pinned inputs, sanitized output |
| Browser | Playwright Chromium, two tenants, DE/EN | failure-only trace/screenshots | deterministic seed; classified setup retry only |
| Container | existing builds/smoke/SBOM/Trivy | immutable commit-bound artifacts | pinned scanner/action inputs |
| Release evidence | existing dependent final job | exact-head checksums/report | no relabelled or stale artifacts |

## Rollout, rollback and completion

No deployment is part of Phase 1. Later rollout uses additive migrations, readers before writers,
configuration/health validation and two-tenant DE/EN smoke tests. Protected execution stays disabled
until artifact storage, residency, retention and independent review are approved.

Before publication, revert the isolated feature if needed. After records exist, retain compatible
readers and migrate forward; never delete the ledger, relabel versions or downgrade records into
Decision File events.

Objective completion requires independent ADR approval; resolved security questions; versioned
schemas; proven binding, independence, isolation, replay/concurrency and failure ordering; green unit,
contract, PostgreSQL, Keycloak, security and browser gates; DE/EN parity; current threat model; no
unresolved critical/high finding; and exact-head release evidence that is not represented as
deployment or organizational approval.
