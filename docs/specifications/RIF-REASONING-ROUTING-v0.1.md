# RIF Reasoning Routing Contract v0.1

**Status:** Proposed design, not implemented — 2026-09-25
**Operating profile:** Development with synthetic or approved test cases
**Decision record:** [ADR-008](../adr/ADR-008-reasoning-routing-boundary.md)

## 1. Objective and decision boundary

The proposed RIF orchestrator selects a reasoning workflow from a finite, policy-approved route set and
hands it a validated machine-readable contract. A route selection does not assert factual truth,
approve evidence, change a business decision or grant execution permission. DA independently
assesses the resulting evidence and proposed action. Maximum credible failure here is a material
case being sent down a cheaper reasoning path or sensitive tenant content leaving an authorized
boundary. The owner of a deployment's routing policy remains accountable for both risks.

The first version covers one routing decision per immutable request snapshot. It does not introduce
an autonomous agent, a live Jev connection, runtime thresholds, a new approval role or a changed
DA state machine. It leaves the provider choice open until comparative evidence exists.
The DA `main` branch has no RIF runtime or upstream `MissionState` contract. This specification
must be reconciled against the authoritative RIF source before claiming RIF conformance or
committing to a module path in DA. See the repository README's RIF/RRS positioning.

## 2. Components and order

1. At the DA integration boundary, authenticate the caller; derive tenant, actor, permitted
   workflow, locale and data classification from trusted context and policy. Verify request
   schema, size, canonical digest and idempotency. An external RIF runtime needs an equivalent
   independently verified identity contract.
2. Apply mandatory route exclusions and external-egress policy before selector invocation. If a
   safe deterministic choice follows, no provider call is needed.
3. Pass an explicitly minimized, policy-approved snapshot and finite candidate set to the selected
   `ReasoningRouterPort`. Local deterministic selection is the default evaluation baseline.
4. Validate the selector signal against the exact candidate-set digest and snapshot. Apply routing
   policy to produce the **effective route**; never equate a proposed route with an authorized one.
5. Persist a redacted append-only routing record before dispatch. Dispatch exactly the effective
   route if the status is `ROUTED`. `ESCALATED` creates a separate routing human handoff;
   `BLOCKED` dispatches nothing. Failure to record a required event prevents automated dispatch.
6. Send reasoning results, evidence and any proposed business action through their existing
   validation, independent judgment and DA governance boundaries.

## 3. Canonical contract shape

`reasoning_route_decision` is a versioned object with `additionalProperties: false` at every
object boundary. The JSON below is *illustrative*; the exact JSON Schema, numeric constraints and
canonicalization algorithm are Phase 1 deliverables. It must not be treated as an executable schema.

```json
{
  "contract_name": "reasoning_route_decision",
  "schema_version": "0.1.0",
  "request_id": "opaque-request-id",
  "tenant_id": "verified-tenant-id",
  "actor_id": "verified-actor-id",
  "snapshot_digest": "hmac-sha256:<hex-of-minimized-canonical-input>",
  "snapshot_digest_key_id": "approved-key-version-id",
  "candidate_set_digest": "sha256:<hex-of-canonical-options-and-criteria>",
  "policy_digest": "sha256:<hex-of-immutable-policy-content>",
  "candidate_routes": ["FAST_REASONING", "FULL_REASONING", "HUMAN_REVIEW"],
  "required_specialist_capability": null,
  "selector": {"kind": "deterministic", "provider": "local", "version": "version-id"},
  "proposed_route": "FULL_REASONING",
  "signal": {"probabilities": null, "confidence": null},
  "status": "ROUTED",
  "effective_route": "FULL_REASONING",
  "policy_version": "routing-policy-version",
  "reason_codes": ["ROUTE_POLICY_APPLIED"],
  "correlation_id": "opaque-correlation-id"
}
```

`tenant_id` and `actor_id` are derived at the authenticated boundary and may never be accepted
from selector output. `snapshot_digest` binds the exact approved, minimized input, tenant,
classification and locale metadata where routing relevant; it is not a license to retain raw
content. Use a tenant-bound keyed digest when minimized inputs are sensitive or guessable, with
key version, rotation and verification rules. `candidate_set_digest` binds route labels, meanings,
specialty constraints and policy criteria, not just the array order. `policy_digest` binds
immutable policy content in addition to its human-readable version. Define a canonical JSON
algorithm and domain separators before computing digests. `candidate_routes` are the exact
options submitted to the selector after hard exclusions, including any explicit human escalation
option. `proposed_route` is the untrusted selector result; `effective_route` is the policy outcome.
The persisted contract records both, including explicit abstention or outage reason codes when no
valid proposal exists; the schema must then allow `proposed_route: null` and `selector: null`
when preflight stops invocation. `status` is `ROUTED`, `ESCALATED` or `BLOCKED`. `BLOCKED` must
have `effective_route: null`; `ESCALATED` must have `HUMAN_REVIEW`; a routed
`SPECIALIST_REASONING` requires a policy-approved non-null
specialist capability. More than one required specialty needs a separate multi-step workflow or
human escalation.

`signal.probabilities` is optional and must either cover exactly the submitted candidate set with
finite values in [0, 1] summing to 1 within a declared tolerance, or be `null`. Selector confidence
is separately optional and must carry documented provider semantics before use; do not derive it
as `1 - uncertainty` or as the top probability. Until calibrated, probabilities and confidence
are diagnostic evidence only and cannot authorize a cheaper route. Selectors must be version
identified; aliases with mutable behavior cannot support reproducible pilot or production claims.

Supported code values are language-neutral. DE/EN user and audit-display messages use localization
keys; input language and user locale are distinct and an unsupported or unsafe translation cannot
silently change route. The v0.1 JSON Schema must constrain required fields, enums, identifier
lengths, digests, bounds, unknown fields and all nullable/abstention cases.

## 4. Policy and failure rules

- Evaluate hard constraints (risk, legal or regulated domain, data sensitivity, tenant entitlement,
  locality, required specialty, available tools and human-review requirement) before probabilistic
  selection. Provider output cannot relax them. `SPECIALIST_REASONING` requires an explicit
  capability and an eligible specialist; otherwise escalate.
- Derive permitted routes from trusted policy and claims. A missing policy, ambiguous identity,
  wrong tenant, incompatible contract or failed integrity check blocks routing. A provider failure
  may use a documented local safe route only where policy proves it satisfies every hard constraint;
  otherwise route to `HUMAN_REVIEW` or return a typed blocked result.
- Do not invent numeric cutoffs. Record a threshold policy proposal only after blinded labels,
  calibration and false-fast evaluation with a deterministic baseline. A high score never overrides
  a mandatory exclusion. Any downshift after new evidence requires a new versioned route decision.
- Use stable reason codes and append-only `routing.decision` plus `routing.egress-decision` events.
  Bind events to tenant, actor, request, snapshot, candidate set, selector version, policy version,
  proposed/effective route, UTC time and correlation ID. Redact secrets, raw prompts and personal
  content. Idempotent replay returns the same result; a reused ID with a different digest fails.
- External selectors require a separate allowlisted request-time egress guard, residency and
  subprocessor evidence, bounded timeout/retry/cost, approved secret provider and no network call
  on preflight or audit failure. The current deployment profile is authoritative.
- A routing `HUMAN_REVIEW` handoff needs a case reference, authenticated reviewer and scope-bound
  instruction to re-evaluate the route. It is not a DA approval. Reentry creates a new route
  decision linked to the previous event; the original cannot be silently overwritten.

## 5. Threats and controls

| Threat | Design control | Verification target |
| --- | --- | --- |
| Prompt injection in task text selects a privileged route | text is data; fixed route set and deterministic policy | adversarial route test |
| Cross-tenant request or replay | verified tenant, tenant-bound hashes and idempotency | two-tenant negative API/E2E test |
| False fast on material work | preflight exclusions, safe fallback and benchmark threshold gate | zero forbidden downshifts; measured false-fast |
| Sensitive data sent to provider | minimization, classification and egress guard | zero-call and redaction tests |
| Selector drift or invalid distribution | version pin, strict mapping, shape and calibration checks | contract and regression tests |
| Outage, timeout or lost audit | bounded failure and typed escalation/block | failure-injection E2E |
| Self-approval or DA bypass | route has no assurance or execution authority | negative role and action-binding tests |

## 6. Design verification matrix

`NOT TESTED` means the proposed control has not yet been implemented or verified.

| Requirement | Risk | Control | Evidence | Test or gate | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Input and contract integrity | substituted route | strict schema, canonical hashes | this design only | schema and tamper tests | RIF maintainer | NOT TESTED |
| Authentication and authorization | untrusted caller | verified identity and central permissions | existing repository mechanisms; wiring pending | API role negatives | API owner | NOT TESTED |
| Multitenancy | cross-tenant leakage | tenant-bound context and persistence | design only | two-tenant negative E2E | API owner | NOT TESTED |
| Multilingual behavior | unsafe locale fallback | stable codes, DE/EN display and locale tests | design only | German/English E2E | UI owner | NOT TESTED |
| Egress and data residency | unauthorized transmission | preflight plus request-time guard | design only | denied-call spy and regional gate | Security owner | NOT TESTED |
| Secrets, privacy and retention | credential/PII disclosure | secret port, redaction, minimized retention | design only | canary scan and retention tests | Security owner | NOT TESTED |
| Actor independence and audit | implicit approval | distinct DA authority, append-only route events | design only; route event type and durable store absent | bypass and audit failure tests | DA owner | NOT TESTED |
| Failure and rollback | silent fast fallback | typed safe escalation and stop switch | design only | outage, retry, restore E2E | Operations owner | NOT TESTED |
| Benchmark and release | false fast | versioned labels and decision gate | design only | baseline comparison and review | RIF owner | NOT TESTED |

## 7. Open decisions for independent review

1. Identify the authoritative upstream RIF contract/owner and settle whether the reference router
   is hosted in DA or a separate RIF package. The current DA `main` has no RIF runtime. Confirm the
   event registry, durable routing audit and export mapping in the implementation revision;
   existing Web Research egress controls are a pattern, not evidence that routing uses them.
2. Establish route eligibility, specialty identifiers, exact nullable schema cases, human handoff,
   canonicalization/key lifecycle, audit retention and performance/cost budgets. Database-level
   append-only enforcement for new events must be proven before relying on it for a pilot.
3. Decide which tenant data classes and regions may reach an external provider, based on its
   verified contract, processing, support access and retention terms.
4. Define independent labels, safety-weighted acceptance criteria and responsible human reviewers
   before any threshold or vendor comparison is accepted.
