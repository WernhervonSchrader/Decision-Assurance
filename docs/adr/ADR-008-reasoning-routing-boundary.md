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
authenticated, tenant-bound request enters the orchestrator. Mandatory risk, scope and data-policy
constraints are checked before any external call. A selector may propose one route from a
policy-defined finite set. A separate deterministic routing policy validates the candidate set,
selector response and constraints, then records an effective route and reason codes. Failure,
missing data or disallowed downgrade goes to the policy-defined safe route or human review; it
never silently selects a cheaper route. The effective route controls reasoning workflow only.

Routing, substantive judgment and execution authorization are different decisions. Neither the
selector nor the orchestrator can issue `PASS`, `APPROVED`, `ALLOW_EXECUTION` or a substitute DA
finding. Evidence and results enter the existing independent DA boundary; execution still requires
the applicable DA outcome and action binding. The selector cannot approve its own output.

The initial route vocabulary is `FAST_REASONING`, `FULL_REASONING`, `SPECIALIST_REASONING` and
`HUMAN_REVIEW`. `SPECIALIST_REASONING` is capability-specific, not an ordinal rank; the required
specialty must be explicit. `HUMAN_REVIEW` is an escalation route, not a machine approval. Policy
may prohibit `FAST_REASONING` for defined risk or data classes before invoking a selector.
The routing human handoff is distinct from the DA Decision File `REVIEW` state. It requires its
own actor-bound handoff and a new recorded routing decision before resuming automated work.

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
