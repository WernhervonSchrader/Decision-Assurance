# ADR-008: Provider-neutral reasoning routing before Decision Assurance

**Status:** Proposed for independent review — 2026-09-25
**Operating profile:** Development; documentation only
**Related specification:** [RIF Reasoning Routing v0.1](../specifications/RIF-REASONING-ROUTING-v0.1.md)

## Context

RIF needs a machine-readable choice of reasoning path before a task is processed. The choice is
about *how to investigate*, not whether a resulting business action is correct or authorized.
Decision Assurance already has separate evidence, authorization, governance and audit boundaries;
placing a probabilistic route selector inside any of those boundaries would confuse an advisory
signal with authority. A Jev adapter is a candidate selector, subject to evaluation, not a
prerequisite for the architecture. Current provider API, residency and model-version behavior
must be checked against official documentation before any adapter is implemented.

The current `main` contains no RIF orchestrator, `MissionState` implementation or canonical RIF
routing schema. Its README says RIF/RRS research sources are not required to run the DA MVP.
This ADR proposes a new integration boundary in this repository; it does not assert that an
existing RIF component already complies with the proposed contract. The owner and source of the
canonical upstream RIF contract must be identified before runtime code is added.
The [public RIF overview](https://github.com/WernhervonSchrader/Reliable-Intelligence-Framework-Konzept-)
describes the concept but does not publish a normative routing contract.

## Alternatives

1. **Use a provider response as the workflow contract.** Fewer mappings, but provider changes
   become RIF contract changes and may confer accidental authority. Rejected.
2. **Add a separate Jev governance gate.** Gives the selector a misleading approval role and
   duplicates existing DA policy. Rejected.
3. **Define a RIF routing contract and policy, with replaceable selectors.** A deterministic
   baseline runs without an external provider; optional adapters return untrusted signals. The
   orchestrator validates and applies policy before dispatch. Selected.

## Decision

Introduce a versioned, strict machine-readable `reasoning_route_decision` specified for RIF. An
authenticated, tenant-bound request enters the orchestrator. The trusted routing policy first
determines a required, ordered path of validation and reasoning steps from mission risk, scope and
data rules. A selector may then propose one *processing strategy* and supplementary checks from
finite permitted sets. It cannot remove, reorder or mark a required step as complete. A separate
deterministic policy validates the proposal, adds permitted supplementary checks in a governed
order and records the effective strategy, complete path, next step and reason codes. A missing
required capability or check blocks dispatch or creates a human routing handoff;
uncertainty never silently removes a check or chooses a cheaper strategy.
The next outstanding step is derived only from a trusted, revisioned progress record whose
validated results are bound to their step instance, input and validator version. Once accepted,
supplementary steps are part of the effective path and must also be completed. Concurrent
advancement uses compare-and-swap on the progress revision; a selector cannot write progress.

Routing, substantive judgment and execution authorization are different decisions. Neither the
selector nor the orchestrator can issue `PASS`, `APPROVED`, `ALLOW_EXECUTION` or a substitute DA
finding. Evidence and results enter the existing independent DA boundary; execution still requires
the applicable DA outcome and action binding. The selector cannot approve its own output.

The initial *strategy* vocabulary is `FAST_REASONING`, `FULL_REASONING`,
`SPECIALIST_REASONING` and `HUMAN_REVIEW`. `FAST_REASONING` may reduce optional reasoning effort,
never the required validation path. `SPECIALIST_REASONING` is capability-specific, not an ordinal
rank; the required specialty must be explicit. `HUMAN_REVIEW` is an escalation strategy, not a
machine approval. Policy may prohibit FAST for defined risk or data classes before invocation.
The routing human handoff is distinct from the DA Decision File `REVIEW` state. It requires its
own actor-bound handoff and a new recorded routing decision before resuming automated work.
The handoff records the authorized reviewer, scope, result, expiry or cancellation and an atomic
resume transition. A historical route decision may be returned for inspection or idempotent
replay but never grants current dispatch authority. Every dispatch rechecks present authorization,
policy, stop switch, revocation, capability and progress revision; changed conditions require a
new linked decision or a block. Old records remain immutable.

Jev, if used, is an optional provider adapter behind a port. Its claims about probabilities,
confidence, model IDs and API availability are not assumed by the canonical contract. The adapter
must report only verifiable fields; an absent or ambiguous score cannot be fabricated or treated as
calibrated confidence. Route thresholds require a labeled benchmark and documented approval.

## Trust boundaries and consequences

- Canonical contracts cross RIF node boundaries; free text is presentation, never a substitute for
  validated route or governance data. Model output and task text remain untrusted inputs.
- Tenant and actor context come from verified identity; a selector response cannot set either.
  Cross-tenant input, replay, unknown fields and candidate-set changes fail closed.
- External routing is an explicit, guarded egress with data minimization, region and retention
  checks, secret isolation, bounded timeouts and a redacted audit decision before network access.
  If the active deployment profile cannot support the provider, no call is made.
- Record a route decision and egress decision with correlation ID, policy and selector versions,
  immutable policy and candidate-set digests, a protected sanitized-input digest, tenant scope,
  reason codes and effective route. Plain hashes of sensitive or guessable task content are
  insufficient; use keyed digests when that content is involved. Preserve audit append-only
  semantics and avoid storing raw task text or credentials by default.
- Bind the full trusted routing input separately from the minimized selector input, including
  mission revision, immutable node/strategy/capability definitions, policy and candidate criteria.
  Associate responses with server-owned call context and authenticated transport; a digest alone
  proves neither source nor authority. Define canonicalization and digest-key lifecycle.
- Persist the route record, required audit events and uniquely identified dispatch intent in a
  tenant-scoped transaction. A worker rechecks current authority before every attempt, including
  retries and restart recovery. An uncertain external side effect must be reconciled before
  resending; do not infer exactly-once external execution from the outbox.
- A selector outage, incompatible version or missing audit sink prevents an external call or an
  automated downshift. Safe fallback is explicit, observable and tested.
- Hosting a RIF reference implementation inside the DA repository does not make the DA Engine the
  router's owner or give routing permission to existing DA roles. The integration shape and
  separate authorization capability require review before implementation.
- No runtime code, JSON Schema, provider dependency, credential, network call or DA policy change
  is part of this ADR-only pull request. Operational authority remains unchanged.

## Acceptance before implementation

Independent review must approve the contract, policy precedence, data classification, routing
semantics, fallback and evaluation design. The [implementation plan](../specifications/RIF-REASONING-ROUTING-v0.1-IMPLEMENTATION-PLAN.md)
defines verification and release gates; a Draft PR or passing mock tests do not authorize live
provider use, production routing or execution.
