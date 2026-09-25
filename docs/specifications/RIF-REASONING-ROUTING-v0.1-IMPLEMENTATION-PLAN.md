# RIF Reasoning Routing v0.1 — implementation plan

**Status:** Proposed; no production implementation authorized by this document
**Basis:** [ADR-008](../adr/ADR-008-reasoning-routing-boundary.md) and
[routing contract](RIF-REASONING-ROUTING-v0.1.md)
**Starting point:** `main` at `96b32da9e146b3b276c5fec4e636f67f6ea10889`

## Gate 0 — architecture review

An independent reviewer checks the three documents for existing RIF/DA boundaries, authority
separation, contract versioning, deterministic preflight, explicit fallback, data handling and
testability. Confirm that mandatory RIF validation paths can contain multiple nodes and cannot be
replaced by a single FAST/FULL choice. Resolve the four open decisions in the specification.
The first independent review of PR #11 reported six design gaps; this revision addresses their
proposed contract and plan changes, but does not turn that earlier `FAIL` into an approval. Obtain
a new independent review of the revised head and reconcile the authoritative RIF rc3 source.
Confirm target repository paths on the then-current `main` before implementation. Identify the
authoritative upstream RIF source:
`main` contains no RIF orchestrator and explicitly treats RIF/RRS as optional research sources.
Decide whether DA hosts a reference implementation or integrates an independently versioned RIF
package; name contract owner and compatibility test. Without that decision, Stage 1 is `BLOCKED`.
The recommended topology is a RIF-owned normative contract and a version-pinned DA adapter;
approval of the owner, delegated maintenance if any, and a publishable interface subset is still
required. Keep the private full edition, prompts and confidential cases outside this public PR.
The DA repository is public. Review the public/private publication boundary against the public
RIF concept before adding any internal policy logic, prompts, benchmark corpus or provider data.
The development profile uses synthetic or approved data. No provider credential is needed here.

## Stage 1 — provider-neutral contract and deterministic baseline

- Provisional paths, subject to Gate 0 ownership decision:
  `schemas/orchestration/reasoning-route-decision.schema.json`, packaged copy under
  `src/decision_assurance/schemas/orchestration/`,
  `src/decision_assurance/orchestration/{contracts,ports,policy,service}.py`, and
  `src/decision_assurance/orchestration/providers/deterministic.py`. If the contract is owned in
  another repository, publish it there and add only a versioned DA adapter. Update the event
  registry and policy registry through their actual interfaces; do not create duplicate authority.
- Interfaces: `RoutingPolicy.required_path(context) -> OrderedPath`,
  `ReasoningRouterPort.select(call_context, minimized_input, bound_candidates) -> SelectorSignal`,
  and `RoutingPolicy.evaluate(context, path, signal, progress) -> ReasoningRouteDecision`.
  `RoutingBindingPort.commit_manifest(...)` records full and minimized input separately;
  `RoutingProgressPort.read/claim/accept(..., expected_revision)` validates step results and uses
  compare-and-swap; `RoutingDecisionRepositoryPort` stores immutable decisions, handoffs and
  idempotency keys; `RoutingDispatchPort.enqueue/claim/reconcile` stores durable intents; and
  `RoutingAuditPort.append` writes registered route/egress events. Keep trusted actor,
  tenant, data classification, required nodes and permitted strategies outside provider-controlled
  fields. The server-owned call context binds response to manifest, request, policy, candidate and
  path digests. Cover all status/null combinations, early precontract failures and no-work results.
- First write contract tests for canonical and keyed digests, policy-content binding, unknown
  fields, missing/reordered required nodes, forbidden additional nodes, invalid strategies and
  scores, specialist capability/version/executor, the complete status table, six selector outcomes,
  tenant substitution, swapped provider responses, changed definitions and replay conflicts. Then
  implement deterministic preflight,
  baseline selector, versioned policy, trusted progress and append-only redacted route events.
  The current `EventRegistry` does not register `routing.decision`; specify its event schema,
  tenant-scoped durable storage, export and retention path. Add a distinct permission instead of
  borrowing approval capability; review the existing tenant-admin permission expansion.
- On the then-current main, add the next available PostgreSQL migration for tenant-scoped decision,
  handoff, step-progress, idempotency, audit and dispatch-intent tables, plus FORCE RLS and least
  privilege grants. Ordinary application roles must have no UPDATE/DELETE on routing audit rows;
  prove this at the database boundary. Extend the actual registered event schemas and tenant
  export/deletion and retention mechanisms with tested policy durations; avoid claiming existing
  DA audit tables are generally append-only. Commit a decision, required audit record and unique
  intent in one transaction, with a progress-revision CAS where applicable. On failure before
  commit nothing dispatches; after commit a recoverable worker claims the intent and rechecks
  authority immediately before use. A crash after a potentially effective external call is an
  uncertain result: reconcile by provider-supported idempotency key/status lookup or quarantine
  for human resolution before a retry. Do not promise exactly-once remote effects.
- Verify with `python -m pytest tests/orchestration -q`, schema parity checks, Ruff and strict Mypy;
  expected result: every missing check, malformed strategy or forbidden downshift is denied before
  dispatch, the baseline is stable, and no external network is needed.
- Commit boundary: `feat(rif): add typed routing contract and deterministic policy`.

## Stage 2 — optional Jev adapter behind the port

- Before coding, verify current official TypeSafe API/SDK documentation, access terms, response
  fields, model identifier stability, data processing locations, subprocessors and retention.
  Record actual tested SDK/API versions; do not assume previously quoted model IDs or score
  semantics. If these facts cannot be verified or the deployment profile is incompatible, stop
  at Stage 1 and record `BLOCKED` for external integration.
- The official SDK currently defaults to `jev-latest`, may skip unknown answer kinds or ignore
  unknown response fields, and can log unredacted request/response bodies at debug level. The
  adapter must pin an actually available model for evaluated runs, validate completeness against
  the raw protocol response and prohibit body logging. Verify these behaviors again at the
  chosen version: <https://docs.typesafe.ai/sdk/python/usage>.
- Paths: `src/decision_assurance/orchestration/providers/typesafe_jev.py`, provider configuration
  and policy schemas, credential placeholder only, `tests/orchestration/test_jev_adapter.py` and
  an opt-in `tests/orchestration/test_jev_live.py`. Pin any added SDK only after compatibility and
  dependency review; direct bounded `httpx` is an alternative if simpler and officially supported.
- Reuse `SecretProviderPort`, the existing production egress policy and its request-time guard
  pattern, with routing-specific authorization and `routing.egress-decision` audit. Map only
  documented provider fields, preserve raw diagnostic scores safely, and reject unsupported or
  unversioned responses. Never send raw case bodies where minimized fields suffice.
- Configure the selected SDK with internal retries disabled (its documented `RetryPolicy` allows
  `max_retries=0`; see <https://docs.typesafe.ai/sdk/python/api/retries>), or verify and prove a
  guard/audit at every underlying transport attempt. Use
  a bounded adapter-owned retry loop: refresh auth, tenant, policy, stop switch, provider/region,
  approval evidence, secret and remaining budget before each network attempt; durably record each
  egress decision. Fix the allowlisted scheme/host/path, disallow redirects to unexpected targets,
  and enforce a total time and cost ceiling. Revocation between attempts stops the second call.
- Fake-provider contract tests cover timeout, malformed and partial response, wrong candidate
  set, model drift, quota/error, secret redaction, region rejection and zero network calls on
  authorization, preflight or audit failure. Include a failed first attempt followed by policy
  revocation, proving zero second network calls; redirect and total-budget negatives. Live tests
  run only with explicit opt-in, approved
  non-production data and runtime credentials outside Git.
- Commit boundary: `feat(rif): add guarded optional Jev routing adapter`.

## Stage 3 — independent routing benchmark

- Paths: `benchmarks/routing/` with a versioned case manifest, labels and provenance;
  `tests/orchestration/test_routing_benchmark.py` for metric calculations. Do not include
  confidential prompts or cross-tenant records in a public fixture.
- Obtain independently reviewed labels for each case, including its required-node path,
  permissible extra nodes, FAST, FULL, specialist capability and human escalation; stratify DE/EN,
  ambiguity, regulated or sensitive content, tool need, tenant and locale, and known adversarial
  injections. Hold out evaluation cases. Compare local
  deterministic baseline, any existing LLM router if present, and Jev under the same candidate
  set and policy. An absent comparator is reported as absent, not synthesized.
- Report required-path completeness and order, confusion matrix, false-fast numerator/denominator
  by risk class, abstention/escalation, calibration/Brier score only for documented probabilities,
  latency, cost, model-version drift
  and reproducibility. Set acceptable thresholds only from the labeled evidence and independent
  risk review; a single accuracy figure cannot approve a downshift.
- Commit boundary: `test(rif): add reviewed routing benchmark evidence`.

## Stage 4 — integration, E2E and release decision

- Target the existing authenticated API/service boundary without granting the router a DA role.
  Reuse tenant-scoped persistence, central authorization, immutable audit and existing action
  binding. Confirm `routing.decision` events enter the registered audit path and that the
  persistence boundary rejects UPDATE/DELETE in ordinary operation before relying on append-only
  claims. The current filesystem audit pattern alone is not database-level immutability.
- Run API and workflow E2E in an isolated environment using at least two tenants and roles, DE
  and EN, local fake provider, allowed FULL route, prohibited FAST downgrade, wrong tenant,
  stale policy, provider outage, replay, prompt injection, missing audit sink and later DA denial.
  Specifically persist P1 `ROUTED`, revoke under P2, replay P1 and assert no redispatch; then
  create a linked P2 decision. Race two workers on one progress revision; inject a crashed worker
  before commit, after commit, before transport and after an uncertain transport result. Exercise
  accepted supplementary steps, stale validator results, expired/cancelled handoffs, reviewer
  independence, specialist revocation and region denial. Assert tenant RLS across every new table.
  Use deterministic seeds and cleanup, browser coverage only if a user-facing routing review UI
  is introduced. CI retains bounded redacted traces, failures and coverage; remove flaky reliance
  on external providers. Live integration gets a separate opt-in test with no production data.
- Verify route revocation/stop switch, idempotent restart, timeout and bounded retry, secret
  rotation, backup/restore of decision events, tenant export/deletion and retention obligations.
  Record monitoring, alert owner, incident procedure and rollback to deterministic routing.
- Required gates: contract/unit, integration, identity/RBAC, two-tenant isolation, DE/EN locale,
  API E2E, schema parity, Ruff format/lint, strict Mypy, Bandit, dependency and secret scans,
  build and relevant migration checks. Run full repository regression and capture revision,
  environment, exact commands and outcomes. Container scans apply if images change.
- An independent approver reviews benchmark and deployment evidence. A green test run or Draft PR
  is not pilot or production approval. Only a separately authorized release may activate an
  external selector or change default routing.

## Acceptance matrix for implementation

| Requirement | Verification evidence required | Release condition |
| --- | --- | --- |
| Contract and input integrity | public/package schema parity, required-path omission/order, tamper and invalid-value tests | strict validation passes |
| Authentication, authorization and actor independence | role negatives; selector cannot emit DA approval | no bypass |
| Tenant isolation | two-tenant API, persistence and replay negatives | no read/write/inference across tenants |
| Multilingual routing and display | DE/EN equivalence, locale/date formatting and unsafe fallback tests | no silent downgrade |
| Privacy, residency, retention and secrets | approved provider terms, guard zero-call tests, canary scan | verified or external provider blocked |
| Append-only audit and operational failure | event registry/schema, RLS and grants, transactional outbox, outage, retry, restart, uncertain-effect reconciliation, restore and stop tests | no unaudited or stale dispatch |
| E2E and benchmark | reproducible CI E2E and labeled false-fast analysis | independent acceptance decision |

This Draft PR contains only Gate 0's reviewable input. Gate 0 remains `BLOCKED` pending renewed
independent review, authoritative RIF-rc3 reconciliation and the recorded owner/publication/role
and provider decisions. Every implementation and release gate above remains `NOT TESTED` until
executed and recorded at its own commit.
