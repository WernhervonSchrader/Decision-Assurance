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
Confirm target repository paths on the then-current `main` before implementation. Identify the
authoritative upstream RIF source:
`main` contains no RIF orchestrator and explicitly treats RIF/RRS as optional research sources.
Decide whether DA hosts a reference implementation or integrates an independently versioned RIF
package; name contract owner and compatibility test. Without that decision, Stage 1 is `BLOCKED`.
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
  `ReasoningRouterPort.select(snapshot, path_digest, strategies, optional_nodes) -> SelectorSignal`,
  and `RoutingPolicy.evaluate(context, path, signal) -> ReasoningRouteDecision`. Keep trusted actor,
  tenant, data classification, required nodes and permitted strategies outside provider-controlled
  fields. Define nullable abstention, specialist capability and typed blocked outcome in the schema.
- First write contract tests for canonical and keyed digests, policy-content binding, unknown
  fields, missing/reordered required nodes, forbidden additional nodes, invalid strategies and
  scores, specialist capability,
  three statuses and null cases, tenant substitution, absent signals and replay conflicts. Then
  implement deterministic preflight,
  baseline selector, versioned policy, idempotent dispatch and append-only redacted route events.
  The current `EventRegistry` does not register `routing.decision`; specify its event schema,
  tenant-scoped durable storage, export and retention path. Add a distinct permission instead of
  borrowing approval capability; review the existing tenant-admin permission expansion.
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
- Fake-provider contract tests cover timeout, malformed and partial response, wrong candidate
  set, model drift, quota/error, secret redaction, region rejection and zero network calls on
  authorization, preflight or audit failure. Live tests run only with explicit opt-in, approved
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
| Append-only audit and operational failure | route/egress records, outage, restart, restore and stop tests | no unaudited dispatch |
| E2E and benchmark | reproducible CI E2E and labeled false-fast analysis | independent acceptance decision |

This Draft PR completes only Gate 0's reviewable input. Every implementation and release gate
above remains `NOT TESTED` until executed and recorded at its own commit.
