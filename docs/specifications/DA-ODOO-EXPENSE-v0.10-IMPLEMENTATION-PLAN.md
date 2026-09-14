# Decision Assurance v0.10 — Odoo Expense Assurance implementation plan

**Status:** Proposed Phase 1 plan for independent review; no implementation is authorized by this
document.

Normative planning baseline:
`96b32da9e146b3b276c5fec4e636f67f6ea10889`. Implementation must start from the independently
approved head, record its full SHA and re-baseline every contract, test and migration if it differs.
Architecture is defined by [ADR-007](../adr/ADR-007-odoo-expense-assurance-boundary.md) and the
[v0.10 specification](DA-ODOO-EXPENSE-v0.10.md).

## 1. Delivery rules, Phase 1 decisions and exclusions

Every control follows an independently reviewable sequence:

```text
RED: add the prohibited-path or contract test and prove the intended failure
-> GREEN: implement the minimum versioned contract/control
-> REGRESSION: run focused security and compatibility tests
-> COMMIT: include only that control and its tests
```

No production implementation begins before the RED evidence exists. A test that unexpectedly passes
is investigated; it is not accepted as RED evidence. Mandatory unavailable checks fail the release
gate.

Phase 1 makes these explicit decisions:

1. **Identity:** direct DA-verifiable delegated OIDC user tokens are the only enabled Odoo human
   mechanism. The test profile uses locally signed delegated tokens with exact issuer, audience,
   authorized party, subject, tenant, organization, actor-kind, role and scope claims. A token-exchange
   or broker implementation is excluded; if Odoo cannot provide a DA-verifiable delegated token, the
   adapter remains disabled until a separately reviewed contract replaces this decision.
2. **Company mapping:** a generic server-owned `CompanyTenantResolver` runs after authentication and
   before object lookup/ownership authorization.
3. **Registry evolution:** a new versioned `RulePackageRegistry` succeeds the RIF use of the existing
   `PolicyRegistry` through an explicit legacy adapter. Existing `PolicyContext` semantics are not
   changed.
4. **Decision File:** Phase 1 is advisory and compiles Decision File v0.2 with
   `canonical_action = null` and uses `action_digest = null` in any DA lifecycle approval.
   The absence of external action authority does not remove existing Decision Assurance lifecycle
   approval-binding requirements: every approval retains its required fields, Approval Digest and
   single-use nonce. DA lifecycle approval binding is distinct from external execution authorization
   and Odoo execution tokens/reservations. Phase 1 adds no new external execution token. Existing
   v0.2 validation and terminal Transition Policy remain unchanged.
5. **Receipt:** Odoo Action Receipt is post-action evidence only. It is not an authorization, lock,
   reservation, current-validity guarantee or stale-action prevention mechanism.
6. **Mutation:** `COMPILED` Intake is terminal. Material changes create linked successor Intake,
   snapshot, Decision and evaluation artifacts.

Excluded are tax-rule content, BMF packages, DATEV, payment/reimbursement, production Odoo
configuration, OCR provider selection, outbound DA-to-Odoo calls, distributed execution locking,
Canonical-Action-based execution authority and retrospective completed-booking policy. Regular tests
use deterministic fakes and synthetic receipts; no CI test depends on live Odoo, RIF, OCR, public
providers, production identity or customer data.

Protected command ordering is:

```text
authenticate -> derive tenant -> resolve authoritative company mapping
-> authorize actor/role/ownership/object -> validate contract/provenance/state
-> persist required audit decision -> domain mutation -> response
```

Spies prove that denial at any earlier step causes zero later repository, registry, evaluator or
adapter calls.

## 2. Planned architecture, files and interface contracts

### DA Core — existing files expected to change

- `src/decision_assurance/identity.py`, `authorization.py`, `api/dependencies.py`;
- `src/decision_assurance/intake/contracts.py`, `confirmation.py`, `verification.py`, `compiler.py`,
  `repository.py`, `postgresql_repository.py`;
- `src/decision_assurance/decision_file.py`, `engine.py`, `events/registry.py`;
- `src/decision_assurance/repositories/protocols.py`, `repositories/postgresql.py`;
- `src/decision_assurance/api/app.py`, `api/schemas.py`, `api/openapi.py`;
- versioned public and packaged Intake, Decision File, assurance-report and audit schemas;
- `.github/workflows/ci.yml` and applicable architecture/security/API/testing/runbook documents.

### DA Core — new modules

- `src/decision_assurance/provenance/contracts.py` — immutable server-owned provenance;
- `src/decision_assurance/provenance/registry.py` — trusted ingestion/extractor allowlist port;
- `src/decision_assurance/federation/company_tenant.py` — generic resolver contract/service;
- `src/decision_assurance/rule_packages/contracts.py` — immutable authenticated package types;
- `src/decision_assurance/rule_packages/ports.py` — successor registry plus legacy adapter;
- `src/decision_assurance/rule_packages/validation.py` — authority, lineage and selection gate;
- `src/decision_assurance/expense/contracts.py` — presence, Required Fact Set, snapshot, context and validity;
- `src/decision_assurance/expense/canonicalization.py` — versioned snapshot/context hashing;
- `src/decision_assurance/expense/evaluator.py` — pure deterministic machine-rule evaluator;
- `src/decision_assurance/expense/service.py` — application orchestration and successor creation;
- public and packaged schemas under `schemas/provenance/`, `schemas/rule-packages/` and
  `schemas/expense/`;
- `migrations/postgresql/005_expense_assurance.sql` and packaged copy.

### Odoo Adapter — new files

- `src/decision_assurance/integrations/odoo/contracts.py` — untrusted request mapping and receipt evidence;
- `src/decision_assurance/integrations/odoo/service.py` — thin delegation adapter;
- `src/decision_assurance/api/routes/odoo_expenses.py` — authenticated inbound routes;
- versioned Odoo request/response/receipt schemas and packaged copies;
- `migrations/postgresql/006_odoo_expense_receipts.sql` and packaged copy.

Splitting migrations and schemas prevents Odoo-specific persistence from becoming an implicit DA Core
contract and preserves a future `decision-assurance-odoo` repository boundary.

### Required interface shapes

Names may adapt to repository style, but semantics and ordering are fixed:

```text
TrustedProvenanceRegistry.resolve(ingestion_path, extractor_identity, extractor_version, method)
    -> TrustedProvenancePolicy | None
ProvenanceService.bind(server_ingestion, untrusted_observation) -> ProvenanceBinding
CompanyTenantResolver.resolve(identity, source_system, external_org_ref, at_time)
    -> CompanyTenantMapping
RulePackageRegistry.select(tenant, jurisdiction, applicability_hash, at_time)
    -> AuthenticatedRulePackageSelection
RulePackageValidator.validate(selection) -> ValidatedRulePackage
RequiredFactSetResolver.resolve(expense_profile, bootstrap_facts, validated_package)
    -> RequiredFactSet
ConfirmedFactsCanonicalizer.snapshot(case_version, requirements, confirmations)
    -> ConfirmedFactsSnapshot
EvaluationContextBuilder.build(snapshot, requirements, package, evaluator, engine, policies, instant)
    -> EvaluationContext
ExpenseRuleEvaluator.evaluate(snapshot, requirements, validated_package, context)
    -> ExpenseRuleResult
ExpenseAssuranceService.create_successor(previous_case, changed_input, expected_version)
    -> SuccessorArtifacts
OdooExpenseService.record_post_action_evidence(identity, mapping, receipt, idempotency_key)
    -> ActionReceiptEvidenceResult
```

`ExpenseRuleEvaluator` has no network, OCR, LLM, identity, database, Odoo or clock dependency. The
authoritative instant and all numeric/currency/rounding policies arrive through the bound context.

## 3. Test-first task sequence

### Task 0 — Baseline and contract freeze

Read and record the exact HEAD plus Decision File v0.2, Transition Policy, Intake, Identity,
TenantContext, RBAC, engine, repository, RLS, audit, event and idempotency versions. Add a planning
check that fails if implementation begins from a different head without re-baselining.

Expected result: no production change; approved design, threat model, requirements matrix, file map,
test map and commit boundaries refer to `96b32da9e146b3b276c5fec4e636f67f6ea10889`.

Commit: none; planning/review gate.

### Task 1 — RED: versioned contract skeletons

Add failing strict-schema tests before schema/type implementation:

- `tests/provenance/contract/test_provenance_contract.py`;
- `tests/federation/contract/test_company_tenant_mapping.py`;
- `tests/rule_packages/contract/test_rule_package_schema.py`;
- `tests/expense/contract/test_expense_contracts.py`;
- `tests/odoo_adapter/contract/test_odoo_contracts.py`.

Cover exact versions, required fields, unknown-field rejection, authority-field mass assignment,
presence states, Required Fact Set, Evaluation Context, successor references, Execution Validity and
receipt-evidence-only semantics. Assert Decision outcomes remain exactly `PASS/REVIEW/BLOCK` and
Decision File v0.2 remains `canonical_action=null` for this profile.

Before Task 2 or Task 16 implementation, add compatibility cases in
`tests/expense/contract/test_expense_contracts.py`: an advisory Decision File with an existing DA
lifecycle approval, `action_digest=null`, valid Approval Digest and required nonce is contract-valid.
An approval with missing or inconsistent binding fails validation; reused nonces also fail.
Existing v0.2 cases may already pass and are retained as compatibility evidence, not falsely labelled
RED. The new missing expense-profile contracts supply Task 1's intended RED failure.

RED command:
`pytest tests/provenance/contract tests/federation/contract tests/rule_packages/contract tests/expense/contract tests/odoo_adapter/contract -q`.

Expected RED: failures identify missing contracts, never an unrelated import/environment failure.

Commit: `test(expense): define failing v0.10 contracts`.

### Task 2 — GREEN: versioned contracts and compatibility

Implement minimum public/packaged schemas and immutable types. Preserve old Intake, PolicyContext and
Decision File v0.2 meanings. Add explicit compatibility/migration rules; new trust semantics use new
versions. Prove public and packaged copies equivalent and old fixtures unchanged.

GREEN command:
`pytest tests/provenance/contract tests/federation/contract tests/rule_packages/contract tests/expense/contract tests/odoo_adapter/contract tests/contract -q`.

Expected GREEN: Task 1 passes; legacy contract suites remain green.

Commit: `feat(contracts): version expense assurance contracts`.

### Task 3 — RED: trusted source provenance bypasses

Add `tests/provenance/security/test_source_authority.py` and extend compiler contract tests. Required
failing scenarios:

- Odoo submits an OCR value and claims deterministic/trusted source class;
- client sets extractor identity/method, verification class or `confirmation_required=false`;
- unknown, missing, unsupported, unattested or inconsistent provenance;
- valid-looking provenance digest from an unknown ingestion registration;
- 99.9% OCR/LLM confidence, normalized objective value and provider variations;
- alternative candidate/compile endpoint and direct compiler invocation.

Every scenario expects server rejection/ignored authority claim, mandatory confirmation, no automatic
`VERIFIED`, no compilation and zero evaluator calls.

RED command: `pytest tests/provenance/security tests/expense/unit/test_ocr_confirmation_policy.py -q`.

Commit: `test(provenance): expose source authority spoofing`.

### Task 4 — GREEN: server-owned provenance

Implement trusted ingestion registration and immutable Provenance Binding. Authority classification
is derived only from server ingestion context and an exact allowlist; the request model cannot write
authority fields. OCR/LLM and every unknown provenance state default to mandatory confirmation. Add
compiler defense in depth that validates the binding rather than trusting a candidate boolean.

Regression commands:
`pytest tests/provenance tests/intake tests/contract -q`.

Expected: Task 3 green; existing deterministic objective-fact behavior remains only for authenticated
legacy/server-owned methods.

Commit: `feat(provenance): bind fact authority to trusted ingestion`.

### Task 5 — RED: delegated identity and Company/Tenant mapping

Add:

- `tests/federation/security/test_delegated_identity.py`;
- `tests/federation/security/test_company_tenant_resolver.py`.

Failing cases include service token plus forged user, missing/wrong subject or actor kind, wrong
issuer/audience/authorized party, replayed/expired token, client tenant/company override, missing,
ambiguous, expired or revoked mapping, mapping to another tenant and same external company ID in two
source systems. Spies prove zero object lookup/domain access.

RED command: `pytest tests/federation/security tests/production/identity -q`.

Commit: `test(federation): expose delegated identity and company spoofing`.

### Task 6 — GREEN: delegated OIDC profile and generic resolver

Implement only the direct delegated-token profile and generic `CompanyTenantResolver`. Mapping writes
require a separately authorized administrative workflow, optimistic concurrency and append audit.
Unknown or multiple effective mappings fail closed. Do not implement token exchange. If direct token
configuration is absent, disable Odoo human routes at startup/readiness.

Regression command: `pytest tests/federation tests/production/identity tests/production/tenancy -q`.

Commit: `feat(federation): resolve delegated users and company tenants`.

### Task 7 — RED: own-case confirmation authorization

Add `tests/expense/security/test_own_case_confirmation.py`. Fail on foreign owner, wrong tenant,
wrong/revoked company mapping, missing owner, manipulated ID, service/agent actor, terminal Intake,
global confirmation attempt by Generator and payload confirmer/owner fields. Prove no repository
mutation on denial and preserve existing Validator/Approver behavior.

RED command: `pytest tests/expense/security/test_own_case_confirmation.py -q`.

Commit: `test(authz): expose own-case confirmation escalation`.

### Task 8 — GREEN: `INTAKE_CONFIRM_OWN`

Add the narrow permission and centralized object policy only after Tasks 5–6. Establish immutable
owner/mapping references at case creation. Keep `INTAKE_CONFIRM` restricted to existing authorized
flows. Confirmation never changes Decision lifecycle, rules, Odoo approval, booking or payment.

Regression command: `pytest tests/expense/security tests/intake tests/contract -q`.

Commit: `feat(authz): constrain submitter confirmation to owned cases`.

### Task 9 — RED: authenticated Rule Package authority and selection

Add:

- `tests/rule_packages/security/test_registry_authority.py`;
- `tests/rule_packages/unit/test_package_selection.py`;
- `tests/rule_packages/contract/test_policy_registry_adapter.py`.

Fail on self-declared approval, forged/wrong/revoked signature or registry identity, unauthorized or
non-human approver, Rule Author=Rule Approver, wrong tenant/jurisdiction/applicability, future,
expired, revoked, superseded, requested downgrade, hash mismatch, unknown schema/rule version,
unresolved conflict, zero candidates and multiple applicable candidates. Assert zero evaluator calls.
Legacy `PolicyRegistry.get_active` fixtures must remain unchanged.

RED command: `pytest tests/rule_packages -q`.

Commit: `test(rules): expose package authority and downgrade failures`.

### Task 10 — GREEN: successor registry, adapter and validator

Implement `RulePackageRegistry`, authenticated provenance verification, approval-authority policy,
author/approver separation, deterministic server selection and lineage/downgrade checks. Implement an
explicit legacy adapter; do not reinterpret `PolicyContext`. Package canonical hashing excludes only
the declared digest/signature fields specified by the versioned canonicalization contract.

Regression command: `pytest tests/rule_packages tests/intake tests/contract -q`.

Commit: `feat(rules): authenticate and select rif rule packages`.

### Task 11 — RED: Required Fact Set and snapshot canonicalization

Add `tests/expense/unit/test_required_fact_set.py` and
`tests/expense/unit/test_snapshot_canonicalization.py`. Fail on missing bootstrap facts, ambiguous
applicability, circular/unknown requirement references, omitted/null/empty presence, duplicate facts,
unconfirmed mandatory provenance, field/map ordering, Unicode policy, decimal/date/currency drift,
changed document/provenance/actor reference and changed canonicalization version.

RED command: `pytest tests/expense/unit/test_required_fact_set.py tests/expense/unit/test_snapshot_canonicalization.py -q`.

Commit: `test(expense): expose incomplete fact-set and snapshot bindings`.

### Task 12 — GREEN: Required Fact Set and Confirmed Snapshot

Implement two stages: the independently versioned Bootstrap Fact Set supplies jurisdiction, expense
profile and package-applicability inputs; candidate selection, package validation and applicability
determination then establish one applicable package. Derive the versioned Required Fact Set from
profile/bootstrap/package requirements, collect and confirm remaining required facts, and only then
create the final Confirmed Facts Snapshot. Unresolved bootstrap preventing unique selection causes
a control stop, never guessing. Preserve original candidates and predecessor linkage.

Regression command: `pytest tests/expense/unit tests/intake -q`.

Commit: `feat(expense): canonicalize required confirmed facts`.

### Task 13 — RED: complete Evaluation Context

Add `tests/expense/unit/test_evaluation_context.py`. Starting from the same facts/package, change each
of evaluator identity/version, DA engine identity/version, fact/package schema or canonicalization,
Required Fact Set, applicability, authoritative instant, numeric policy, currency policy and rounding
policy. Each change must require a different context digest. Unknown/omitted fields fail. Audit
timestamp changes alone must not masquerade as a normative instant change.

RED command: `pytest tests/expense/unit/test_evaluation_context.py -q`.

Commit: `test(expense): expose incomplete evaluation bindings`.

### Task 14 — GREEN: Evaluation Context digest

Implement canonical context construction and persist explicit component versions/digests. Document
every nested digest and covered fields. Equal full contexts hash identically; any normative drift
hashes differently.

Regression command: `pytest tests/expense/unit/test_evaluation_context.py tests/contract -q`.

Commit: `feat(expense): bind complete executable evaluation context`.

### Task 15 — RED: total rule semantics and deterministic evaluator

Add `tests/expense/unit/test_expense_evaluator.py`. Cover every row of specification section I,
including unknown with/without review permission, deterministic non-applicability and separation of
control failures from fachlich results. Fail if an LLM, network, identity, database, Odoo or ambient
clock dependency is introduced. Repeat/permutate inputs and assert stable rule IDs, calculations,
reason codes and outcomes.

RED command: `pytest tests/expense/unit/test_expense_evaluator.py -q`.

Commit: `test(expense): define total deterministic rule semantics`.

### Task 16 — GREEN: evaluator and Decision binding

Implement pure machine-readable rules, compile their contributions to existing Decision constraints
and let only the existing DA Engine produce outcomes. Persist Decision/evaluation, report, complete
context and audit atomically. Preserve the outcome and lifecycle enums. Phase 1 compiler explicitly
emits Decision File v0.2 `canonical_action=null`. Run the Task 1 compatibility cases: an existing
DA lifecycle approval still requires a valid Approval Digest and nonce with `action_digest=null`;
missing/inconsistent bindings fail. No new external execution token or Odoo authority results.

Regression command: `pytest tests/expense tests/test_decision_file.py tests/test_transitions.py -q`.

Commit: `feat(decision): evaluate advisory expense assurance`.

### Task 17 — RED: terminal mutation and successor artifacts

Add `tests/expense/security/test_versioned_mutation.py`. Attempt to reopen `COMPILED`, mutate v1
snapshot/Decision/evaluation, reuse v1 identity for v2 and reactivate a superseded evaluation. Cover
stale concurrent writer, duplicate invalidation/supersession, audit failure and partial transaction
failure. All direct historical mutations fail.

RED command: `pytest tests/expense/security/test_versioned_mutation.py -q`.

Commit: `test(expense): expose terminal artifact mutation`.

### Task 18 — GREEN: successor lifecycle and validity

Create linked Intake/snapshot/Decision/evaluation v2 without reopening v1. Use compare-and-set for
`ACTIVE -> INVALIDATED -> SUPERSEDED`, preserve historical outcome/context and make transitions
audited/idempotent. There is no reverse transition to `ACTIVE`.

Regression command: `pytest tests/expense/security/test_versioned_mutation.py tests/intake tests/test_transitions.py -q`.

Commit: `feat(expense): create versioned assurance successors`.

### Task 19 — RED: Odoo adapter boundary before adapter code

Add `tests/odoo_adapter/security/test_adapter_boundary.py` before routes/services. Fail on missing or
invalid delegated identity, authority-field mass assignment, wrong mapping/owner/tenant, direct
outcome/approval assignment, unbounded payloads and attempts to select a package. Dependency tests
fail if the adapter adds outbound HTTP, Odoo admin secrets, embedded evaluator/policy logic, booking,
payment or DATEV behavior.

RED command: `pytest tests/odoo_adapter/contract tests/odoo_adapter/security/test_adapter_boundary.py -q`.

Commit: `test(odoo): define inbound advisory adapter boundary`.

### Task 19a — RED: E2E and Golden journeys before route/adapter wiring

Before Task 20, create the E2E journeys under `tests/expense/e2e/` and Golden fixtures/tests under
`tests/gold/expense/`. Use FastAPI's in-process client, deterministic Odoo fake and isolated
PostgreSQL 16, with German/English, two tenants/companies and the planned actor roles.

The journey is authenticated identity -> company/tenant resolution -> candidate intake ->
confirmation of Bootstrap Facts -> Rule Package candidate selection -> package validation ->
applicability determination -> Required Fact Set -> collection/confirmation of remaining facts ->
final Confirmed Facts Snapshot -> evaluation_context_digest -> deterministic evaluation ->
assurance result. The Golden flow then includes Odoo-owned action, receipt evidence and reconstruction.
Define all positive/negative journeys listed in Tasks 25 and 26 here.

RED commands: `pytest tests/expense/e2e -q` and `pytest tests/gold/expense -q`.
Expected RED: the DA API/Odoo adapter routes and cross-boundary orchestration do not yet exist;
the valid journey cannot obtain its expected assurance response. Receipt/persistence portions also
remain unwired until Tasks 22/24. Do not introduce artificial failures, broken fixtures or environment
errors. Preserve the same tests for subsequent GREEN runs.

Commit: `test(odoo): define failing e2e and golden journeys before wiring`.

### Task 20 — GREEN: thin inbound Odoo adapter

Expose only bounded create/read/candidate/confirm/evaluate endpoints required by the Golden Case.
Delegate to the same identity, resolver, authorization, provenance, Intake, registry, evaluator,
repository and engine services. Regenerate and compare OpenAPI. No outbound Odoo transport exists.
This implements the missing assurance-path wiring identified by Task 19a; receipt and PostgreSQL
completion follow in Tasks 22/24. Full E2E/Golden GREEN is verified in Tasks 25/26.

Regression command: `pytest tests/odoo_adapter tests/contract -q`.

Commit: `feat(odoo): add inbound advisory expense adapter`.

### Task 21 — RED: receipt is evidence only

Add `tests/odoo_adapter/security/test_action_receipt_evidence.py`. Prove receipt submission cannot:

- authorize or perform an Odoo action;
- change `PASS/REVIEW/BLOCK` or Decision lifecycle;
- mark DA or Odoo approval;
- create booking/payment authority;
- claim stale-action prevention.

Cover wrong tenant/mapping/case, malformed/duplicate/changed payload, expired identity, unsupported
action type and audit failure. Include the race where an evaluation changes after Odoo read but before
external execution: expected evidence records the observed discrepancy/residual risk and never claims
that DA prevented the external action.

RED command: `pytest tests/odoo_adapter/security/test_action_receipt_evidence.py -q`.

Commit: `test(odoo): constrain receipts to post-action evidence`.

### Task 22 — GREEN: post-action receipt evidence

Implement strict receipt validation and tenant/case-scoped idempotency. Same key/payload replays;
changed payload conflicts. Persist received evaluation/context references and discrepancy codes as
evidence without changing authority or lifecycle. Name APIs/types with `post_action_evidence` where
practical to prevent stronger claims.

Regression command: `pytest tests/odoo_adapter -q`.

Commit: `feat(odoo): record post-action receipt evidence`.

### Task 23 — RED: PostgreSQL/RLS and audit privileges

Before migration implementation, add PostgreSQL tests for tenant-composite keys, mapping/provenance/
package/snapshot/context/successor/receipt isolation, cross-tenant foreign keys, missing tenant
context, same external IDs, rollback and idempotency. As the real runtime role, attempt `UPDATE`,
`DELETE` and `TRUNCATE` on every append-only audit/evidence table and expect database denial.

Files:

- `tests/production/postgresql/test_expense_tenant_isolation.py`;
- `tests/production/postgresql/test_expense_migrations.py`;
- `tests/production/postgresql/test_audit_privileges.py`.

RED command: `pytest -m postgresql tests/production/postgresql/test_expense_tenant_isolation.py tests/production/postgresql/test_expense_migrations.py tests/production/postgresql/test_audit_privileges.py -q`.

Commit: `test(postgresql): expose expense isolation and audit grants`.

### Task 24 — GREEN: split persistence and privilege hardening

Implement migrations 005/006 and packaged copies. Use forced RLS, tenant-composite constraints and
separate application, worker, migration, readonly and audit-export roles. State/audit/idempotency
writes are atomic. Revoke runtime update/delete/truncate from append-only structures while retaining
minimum select/insert or reviewed append functions. Document and audit privileged migration/recovery
authority; describe records as append-only for runtime and tamper-evident, not absolutely immutable.

Regression command: `pytest -m postgresql tests/production/postgresql -q`.

Commit: `feat(postgresql): persist isolated expense evidence`.

### Task 25 — GREEN: commit-bound Golden Evidence Set

Run the same Golden tests and synthetic German/English fixtures created in Task 19a, after Tasks
20/22/24 have implemented the missing API/adapter, receipt and persistence orchestration. Bind one
evidence manifest to the exact implementation commit, schema versions, fixture hashes and test IDs.
The set contains:

- positive trusted-provenance/correction/Bootstrap Facts/package candidate selection/validation/
  applicability/Required Fact Set/remaining confirmation/final snapshot/context/outcome/Odoo-action/
  receipt/audit flow;
- N1 99.9% unconfirmed OCR;
- N2 forged deterministic/trusted source claim;
- N3 attempt to reopen compiled v1 and required linked v2;
- N4 foreign/ambiguous/revoked company mapping;
- N5 forged/self-approved/revoked/expired/conflicted/ambiguous/downgraded package;
- N6 evaluator/canonicalization/instant/numeric/currency/rounding drift;
- N7 visible external stale-action residual risk and receipt-evidence-only behavior.

RED evidence comes from Task 19a's genuinely absent cross-boundary orchestration.
GREEN command: `pytest tests/gold/expense -q` after Tasks 20/22/24 complete that orchestration.
The same journey assertions must pass without weakening the tests.

Expected: all positive and prohibited journeys plus complete audit reconstruction pass as one
commit-bound evidence set.

Commit: `test(expense): prove remediated odoo golden evidence set`.

### Task 26 — GREEN: security and E2E

Run the unchanged journey definitions created in Task 19a under `tests/expense/e2e/`, after
route/adapter implementation and receipt/persistence completion in Tasks 20/22/24. Use FastAPI's
in-process client, deterministic Odoo fake and isolated PostgreSQL 16 with two tenants, two companies,
submitter, validator/approver, service actor and auditor in German and English. Cover authentication,
session expiry, logout, authorization, ownership, mapping, tenant isolation, validation, terminal
transitions, replay, partial transaction/audit failure, review/block and receipt discrepancy.

The scope is API-only; browser/device coverage is inapplicable because Odoo UI is external and not
implemented here. CI retains sanitized JUnit and server traces on failure; no receipt body, token,
mapping secret or credential enters artifacts. Tests use fresh per-run data and no retries.

RED evidence: Task 19a, before Task 20 route/adapter wiring.
Visible dependency order: Task 19a E2E RED -> Tasks 20/22/24 implementation -> Task 26 E2E GREEN.

GREEN command: `pytest tests/expense/e2e tests/gold/expense -q` after wiring.

Commit: `test(expense): prove authority tenant and advisory boundaries`.

### Task 27 — Full CI, documentation and commit-bound evidence run

Update architecture, threat model, API, identity, tenant, testing, E2E, deployment, retention,
incident, recovery and Decision File integration documentation to describe only implemented behavior.
Update OpenAPI, event registry/export recognition, localization catalogs and migration checks.

Run formatting, lint, strict typing, unit/contract/integration/PostgreSQL/RLS/E2E, schema/OpenAPI,
migration/rollback, dependency audit, secret scan, static analysis, build, container/SBOM/scan and
recovery/release evidence gates. Bind outputs plus independent specification/security and separate
code-quality review to the exact full head SHA.

This proves repository/integration evidence only. It does not deploy, approve tax content, close the
external stale-action residual risk or authorize production Odoo use.

Commit: `docs(expense): document verified advisory assurance boundary`.

## 4. Verification commands and expected results

Run with repository-supported exact tool versions:

```text
python -m pytest -q
python -m pytest -m postgresql -q
python -m ruff format --check src tests
python -m ruff check src tests
python -m mypy src
python -m bandit -q -r src -s B105
decision-assurance-openapi --api-version <approved-version> <temporary-output>
git diff --no-index --exit-code -- docs/openapi-<approved-version>.json <temporary-output>
python -m build
git diff --check
```

Expected results:

- all regular and PostgreSQL tests pass;
- public/packaged schemas and migrations match;
- Decision File v0.2 compatibility and terminal transitions remain green;
- OpenAPI has no unexplained drift;
- mandatory security scans have no unresolved critical/high findings;
- images build/run non-root;
- no secret, token or receipt canary appears in logs/artifacts;
- Golden Evidence Set manifest and results bind to the exact commit;
- the N7 race test reports the Phase 1 residual boundary, not stale-action prevention.

CI retains actionable JUnit, sanitized traces, migration output, security reports and commit-bound
release evidence under the existing retention policy. Controlled reruns may diagnose infrastructure
flakiness but do not erase the first result.

## 5. Commit and independent-review boundaries

Each listed commit includes its scoped RED/GREEN control and compatible regression evidence. A RED
test commit may intentionally fail only its named missing control; no unrelated failing baseline is
accepted. Before PR publication, verify expected head, changed scope, schemas, migrations, docs and
all mandatory checks.

Independent review evaluates source-authority bypasses, federation, resolver uniqueness, ownership,
RIF approval/lineage, complete evaluation context, terminal artifact versioning, Decision File v0.2
advisory semantics, receipt non-authority, RLS and audit privileges against the exact head. Merge and
deployment remain separate explicit authorizations.

## 6. Completion evidence and acceptance gate

Phase 1 is complete only when every v0.10 acceptance criterion has a passing test or concrete
commit-bound evidence; every prohibited path stops before sensitive DA processing; the Golden
Evidence Set passes; migrations/rollback and audit roles are verified; no unresolved critical/high
defect remains; and independent specification/security plus code-quality reviews report no blocker.

Completion does not claim prevention of the external Odoo stale-result race. The unresolved
retrospective revocation policy and any future Canonical-Action execution protocol remain explicitly
outside Phase 1.

## 7. Independent-review finding closure matrix

| Finding | Normative closure | RED evidence | GREEN boundary |
| --- | --- | --- | --- |
| B-01 Source authority spoofing | server-owned Provenance Binding; untrusted authority fields cannot grant trust | Task 3 | Task 4 |
| B-02 post-action TOCTOU claim | receipt is evidence only; stale external execution prevention is an explicit non-goal | Task 21 and Golden N7 | Task 22 |
| B-03 incomplete evaluation binding | complete canonical Evaluation Context and digest | Task 13 and Golden N6 | Task 14 |
| M-01 stale baseline/Decision File v0.2 | exact `96b32da...` baseline; advisory `canonical_action=null`; existing lifecycle Approval Digest/nonce retained; no new external execution token | Tasks 0–2 and 16 | advisory approval positive/negative compatibility suites |
| M-02 registry/approval ambiguity | versioned successor port, legacy adapter, authenticated authority, actor separation and lineage | Task 9 and Golden N5 | Task 10 |
| M-03 identity/company sequencing | direct delegated OIDC decision and generic resolver precede own-case authorization | Tasks 5 and 7 | Tasks 6 and 8 |
| M-04 terminal Intake contradiction | no reopening; linked successor artifacts and separate validity | Task 17 and Golden N3 | Task 18 |
| M-05 incomplete unknown semantics | total result table, applicability bootstrap and versioned Required Fact Set | Tasks 11 and 15 | Tasks 12 and 16 |
| M-06 incomplete test-first order | control RED precedes GREEN; E2E/Golden RED in Task 19a precedes route wiring | Tasks 1–19a and 21/23 | implementation 20/22/24; Golden/E2E GREEN 25/26 |
| MIN-01 audit overclaim | append-only for runtime and tamper-evident; privileged DB authorities remain explicit | Task 23 | Task 24 |
