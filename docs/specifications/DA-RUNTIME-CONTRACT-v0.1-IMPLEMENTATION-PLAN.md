# Runtime Contract v0.1 — Implementation Plan

**Status:** Proposed after self-review; implementation is not authorized

**Documentation-remediation basis:** `fb30152492a01776a3228aac5f3b933337cd67ae`

**Future implementation base:** must be selected and independently approved at implementation time

**ADR:** [ADR-007](../adr/ADR-007-runtime-contract-execution-evidence.md)

**Specification:** [Runtime Contract v0.1](DA-RUNTIME-CONTRACT-v0.1.md)

## Scope and constraints

After independent approval, implement the smallest standalone Runtime Contract described by ADR-007.
Do not modify Decision File v0.2 semantics, introduce general tracing, store prohibited raw content,
claim production non-bypassability, deploy or grant organizational acceptance.

Use test-driven tasks. Preserve tenant context through API, service, repositories, jobs, events,
caches and artifact resolution. Stage, commit, push and PR creation each require authorization.

This document plans future work only. No control below is implemented or evidenced by this plan.
Every future test, control and gate has status `NOT TESTED` until commit-bound evidence records an
actual execution. `NOT TESTED` must never be rendered as `PASS` or omitted from a mandatory gate.

## Proposed architecture

```text
Verified OIDC Identity
  -> Tenant + Authorization Policy
  -> Runtime Contract Binder
  -> Execution Authorization Gate
  -> Atomic Attempt Reservation + execution.attempt_reserved
  -> execution.attempt_started
  -> Protected Target Port
  -> Reconciliation Record when EFFECT_UNKNOWN
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

Cover the field-exact canonicalization matrix, RFC 8785/domain separation/timestamp rules, closed
value namespaces, the two closed artifact schemas, the lossless Decision File v0.2 approval mapping,
`runtime_decision_reference_digest`, valid contracts, unknown fields/version/algorithm, every binding mutation, missing/stale/
unavailable evidence, circular provenance, replay IDs and deterministic key ordering. Assert codes,
not localized prose.

Prove that imported v0.2 action/approval digests use the unchanged v0.2 reference functions, that no
v0.2 full-document digest is assumed, and that Runtime-owned digests alone use the new RFC 8785 and
domain-separation rules. Reject the removed/invented approval field names and every unknown artifact
type, field, version or enum value.

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
atomic state/audit/idempotency, parallel authorization-revocation/reservation races, a distinct durable
`execution.attempt_reserved` event before any target call, duplicate completion, lease loss and rollback.
Parallel tests use at least two connections and prove one effective owner. Failure injection after a
target may have accepted the request must produce `EFFECT_UNKNOWN`, must not return success and must
prove that the orchestrator does not blindly execute the effect again. Cover all reconciliation
outcomes: idempotency inquiry proves effect, independent evidence proves effect, inquiry proves no
effect and authorizes only a new authorization/attempt, and unresolved uncertainty remains
`EFFECT_UNKNOWN` with completion `FAIL`. Verify reconciliation actor independence and append-only
history. Recompute and tamper-test `reconciliation_digest`; prove its exact binding into subsequent
verification and completion, and reject missing, substituted, wrong-tenant or wrong-attempt digests.

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
Authorization revocation and attempt reservation share one compare-and-swap boundary. A committed
revocation returns `AUTHORIZATION_REVOKED` and proves zero adapter calls; a committed reservation
consumes authorization and cannot be retroactively revoked.

### 2.3 Add service and protected execution port

- `src/decision_assurance/runtime_contract/service.py`
- `src/decision_assurance/runtime_contract/execution.py`
- `src/decision_assurance/runtime_contract/evidence.py`
- `tests/runtime_contract/integration/test_execution_ordering.py`

Use dependency-inverted ports and deterministic fakes/spies. Prove zero target/evidence calls before
required gates. Reserve before target I/O; complete only after evidence. Bounded retries must not
repeat an uncertain target effect; reconciliation uses adapter idempotency or independent evidence.
Persist `execution.attempt_started` after reservation and before invoking the protected port.
The ordering spy must observe `authorization_decided -> attempt_reserved -> attempt_started ->
protected I/O`; no overview or adapter path may omit the started event.

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

Cover every cell of the single ADR/spec actor-capability matrix, unknown/mixed-case roles,
Generator/Validator/Approver Protected-I/O denial, role aggregation, service-as-human denial,
two-tenant success; wrong tenant; manipulated action/approval/constraints; authorization revocation,
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

### 4.1 Retention, legal hold, backup and restore evidence

Before enabling artifact storage or protected execution, add deterministic and PostgreSQL tests for
separate ledger/artifact retention, deletion tombstones, the minimum surviving provenance tuple,
tenant-scoped hold application/release, pending delete after hold, authorization-independent hold
access, backup ageing and an isolated fresh restore. Recovery verification must prove holds and
tombstones are re-applied before access, deleted locators are not resurrected, RLS still isolates two
tenants, and the ledger chain/latest retained event matches. Bind observed RPO/RTO to the exact
environment and label them observations. Status: `NOT TESTED`.

Test the exact payloads, capabilities and transitions for `execution.evidence_hold_applied`,
`execution.evidence_hold_released`, `execution.evidence_delete_requested` and
`execution.evidence_delete_completed`. Race hold-apply against delete-complete with two connections;
only one valid CAS transition may win. Prove stale/missing policy, wrong tenant, unauthorized actor,
audit failure and `PENDING_HOLD` delete-complete make no deletion. Verify immutable events contain
only pseudonymous references and that deleting/blocking the external identity mapping leaves every
event byte and hash unchanged.

### 4.2 Decision activation gates

DR-01 and DR-05 are `DEFERRED_CAPABILITY_DISABLED`; DR-07 remains
`DEFERRED_CAPABILITY_DISABLED` until an approved Retention Policy supplies periods. DR-06 and DR-08
are `REQUIRES_DEPLOYMENT_EVIDENCE`. Absence, expiry or mismatch blocks activation. DR-02, DR-03 and
DR-04 are `RESOLVED` only by the exact specification rules and may not be reinterpreted. No
implementation task may silently change a state. Status: `NOT TESTED`.

## Verification matrix

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe format --check .
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe src
.\.venv\Scripts\decision-assurance.exe benchmark benchmarks\dats\v0.1.0\catalog.json
git diff --check
```

| Layer | Strategy | Expected evidence | Flakiness control | Status |
| --- | --- | --- | --- | --- |
| Contract/canonicalization | strict schemas, fixtures, every-field mutation, namespace separation | fixture digests and schema report | fixed clocks/bytes | NOT TESTED |
| PostgreSQL | existing PostgreSQL 16 marker/job, fresh schema | migration/RLS/concurrency/revoke-reserve/rollback | deterministic IDs, barriers, bounded timeouts | NOT TESTED |
| Reconciliation | deterministic fake adapter and independent observation | all `EFFECT_UNKNOWN` outcomes and no blind retry | fixed inquiry responses | NOT TESTED |
| Reconciliation binding | canonical record/digest fixtures and substitution negatives | attempt-to-reconciliation-to-verification-to-completion chain | fixed IDs, clocks and evidence | NOT TESTED |
| Keycloak | isolated Compose realm | PKCE/JWKS/tenant/roles/kind/capabilities | ephemeral secrets and readiness wait | NOT TESTED |
| Retention/recovery | fresh restore with two tenants, holds and tombstones | RLS/hash/latest-event/no-resurrection record | fixed dataset and clocks | NOT TESTED |
| Security | Bandit, audit, Gitleaks, negative tests | no unresolved critical or canary | pinned inputs, sanitized output | NOT TESTED |
| Browser | Playwright Chromium, two tenants, DE/EN | failure-only trace/screenshots | deterministic seed; classified setup retry only | NOT TESTED |
| Container | existing builds/smoke/SBOM/Trivy | immutable commit-bound artifacts | pinned scanner/action inputs | NOT TESTED |
| Release evidence | existing dependent final job | exact-head checksums/report | no relabelled or stale artifacts | NOT TESTED |

## Rollout, rollback and completion

No deployment is part of Phase 1. Later rollout uses additive migrations, readers before writers,
configuration/health validation and two-tenant DE/EN smoke tests. Protected execution stays disabled
until artifact storage, residency, retention periods, legal-hold ownership, backup/restore behavior,
adapter inventory and independent review are approved and evidenced.

Before publication, revert the isolated feature if needed. After records exist, retain compatible
readers and migrate forward; never delete the ledger, relabel versions or downgrade records into
Decision File events.

Objective completion requires independent ADR approval; resolved security questions; versioned
schemas; proven binding, independence, isolation, replay/concurrency and failure ordering; green unit,
contract, PostgreSQL, Keycloak, security and browser gates; DE/EN parity; current threat model; no
unresolved critical/high finding; and exact-head release evidence that is not represented as
deployment or organizational approval.

Until that objective is met, every listed future gate remains `NOT TESTED`; the documentation-only
review remediation does not change that status.

## Publication review corrections, before any implementation

Use constraint_set_digest consistently. Add lossless-source fixtures for valid offset timestamps,
maximum safe positive/negative integers, and denied float/unsafe integer source values; prove the
original v0.2 data and its approval digests remain unchanged and denied imports make zero target calls.
Add Runtime Event 0.1.0 strict fields/version fixtures; existing v1 readers must reject that envelope,
unknown versions/aliases must fail, and the explicit version dispatcher must preserve tenant and hash
bindings. Review: DA-RUNTIME-CONTRACT-v0.1-PUBLICATION-REVIEW.md. All future tests remain NOT TESTED.
