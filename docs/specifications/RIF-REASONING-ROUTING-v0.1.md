# RIF Reasoning Routing Contract v0.1

**Status:** Proposed design, not implemented — 2026-09-25
**Operating profile:** Development with synthetic or approved test cases
**Decision record:** [ADR-008](../adr/ADR-008-reasoning-routing-boundary.md)

## 1. Objective and decision boundary

The proposed RIF orchestrator records the required validation path and a processing strategy in a
machine-readable contract. A route selection does not assert factual truth, approve evidence,
change a business decision or grant execution permission. DA independently assesses the resulting
evidence and proposed action. Maximum credible failures are a material case losing a mandatory
check, using a strategy with insufficient reasoning effort, or sending sensitive tenant content
outside its authorized boundary. The routing-policy owner remains accountable for these risks.

The first version covers versioned routing decisions against an immutable request snapshot; a
change in policy, progress validity or a human resume creates a new linked decision. The required path
may contain multiple ordered steps and cannot be replaced by a single FAST/FULL classification.
It does not introduce an autonomous agent, a live Jev connection, runtime thresholds, a new
approval role or a changed DA state machine. It leaves provider choice open until comparative
evidence exists.
The DA `main` branch has no RIF runtime or upstream `MissionState` contract. This specification
must be reconciled against the authoritative RIF source before claiming RIF conformance or
committing to a module path in DA. See the repository README's RIF/RRS positioning.

## 2. Components and order

1. At the DA integration boundary, authenticate the caller; derive tenant, actor, permitted
   workflow, locale and data classification from trusted context and policy. Verify request
   schema, size, canonical digest and idempotency. An external RIF runtime needs an equivalent
   independently verified identity contract.
2. Determine and bind an ordered **required path** of checks from trusted policy and mission
   context. Apply hard strategy exclusions and external-egress policy before selector invocation.
   If a safe deterministic choice follows, no provider call is needed.
3. Pass an explicitly minimized, policy-approved snapshot, required-path digest, finite strategy
   candidates and permitted optional nodes to `ReasoningRouterPort`. Local deterministic
   selection is the baseline. The selector may suggest extra nodes but cannot edit the required
   path.
4. Validate the signal against the exact candidate and required-path digests. Deterministic policy
   merges eligible additional nodes into the path according to a versioned precedence rule and
   produces the **effective strategy**, complete path and next node. A proposal is neither
   authorization nor evidence that a check ran.
5. Atomically persist a redacted append-only decision, required audit event and uniquely
   identified dispatch intent. A worker independently rechecks current authority and trusted
   progress before dispatching the next outstanding effective node. `ESCALATED` creates a human
   handoff; `BLOCKED` dispatches nothing. Failure to record a required event prevents dispatch.
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
  "decision_id": "opaque-decision-id",
  "predecessor_decision_id": null,
  "tenant_id": "verified-tenant-id",
  "actor_id": "verified-actor-id",
  "mission_revision": "immutable-mission-revision",
  "progress_revision": 0,
  "snapshot_digest": "hmac-sha256:<hex-of-full-trusted-routing-input>",
  "selector_input_digest": "hmac-sha256:<hex-of-actual-minimized-provider-input>",
  "snapshot_digest_key_id": "approved-key-version-id",
  "binding_manifest_digest": "sha256:<hex-of-versioned-binding-manifest>",
  "definition_catalog_digest": "sha256:<hex-of-immutable-node-strategy-capability-definitions>",
  "candidate_set_digest": "sha256:<hex-of-canonical-options-and-criteria>",
  "policy_digest": "sha256:<hex-of-immutable-policy-content>",
  "required_path": ["SOURCE_VALIDATION", "CONSTRAINT_VALIDATION", "REASONING"],
  "required_path_digest": "sha256:<hex-of-ordered-required-path>",
  "permitted_additional_nodes": [],
  "proposed_additional_nodes": [],
  "effective_path": ["SOURCE_VALIDATION", "CONSTRAINT_VALIDATION", "REASONING"],
  "effective_path_digest": "sha256:<hex-of-ordered-effective-path>",
  "required_next_node": "SOURCE_VALIDATION",
  "handoff_reference": null,
  "candidate_strategies": ["FAST_REASONING", "FULL_REASONING", "HUMAN_REVIEW"],
  "required_specialist_capability": null,
  "selector": {"kind": "deterministic", "provider": "local", "version": "version-id"},
  "selector_outcome": "ANSWERED",
  "provider_call_id": null,
  "proposed_strategy": "FULL_REASONING",
  "signal": {"probabilities": null, "confidence": null},
  "status": "ROUTED",
  "effective_strategy": "FULL_REASONING",
  "policy_version": "routing-policy-version",
  "reason_codes": ["REQUIRED_PATH_BOUND", "STRATEGY_POLICY_APPLIED"],
  "correlation_id": "opaque-correlation-id"
}
```

`tenant_id` and `actor_id` are derived at the authenticated boundary and may never be accepted
from selector output. `snapshot_digest` commits to the full trusted routing-relevant mission
snapshot, including tenant, classification, locale where relevant and `mission_revision`;
`selector_input_digest` separately commits to the exact minimized input sent to the selector.
Neither licenses retaining raw content. Sensitive or guessable input uses tenant-bound keyed
digests; public immutable definitions may use SHA-256. The versioned, immutable binding manifest
includes request and mission IDs/revisions, trusted input commitment and its provenance, policy
content/version, complete node/strategy/specialist definition catalog with validator and
capability versions, candidate meanings and eligibility criteria, ordered required path,
minimization/template version and exact selector input commitment. Its canonicalization algorithm,
domain separators, key IDs and verification procedure must be versioned. Verification keys require
controlled access, rotation, revocation and retention at least as long as the decision's required
verification window; after lawful key destruction verification must be reported unavailable, not
silently passed. A digest does not authenticate the author. Across trust boundaries use
authenticated transport and verified identity. The server binds each provider response to its
own unique call ID, tenant, request, policy, candidate/path digests and manifest; response-supplied
identifiers cannot establish this association. `provider_call_id` is null when no external call
occurs. `candidate_set_digest` binds strategy labels, meanings, specialty constraints and
permitted additional nodes. `policy_digest` binds immutable policy content in addition to its
human-readable version. `required_path` is a policy-derived ordered set of required nodes.
`effective_path` preserves their relative order and may contain only policy-permitted additional
nodes; after acceptance all its steps are mandatory. `required_next_node` is the first outstanding
effective node according to verified progress. `FAST_REASONING` can adjust optional effort but
cannot delete, reorder or satisfy any required node.
`candidate_strategies` and `permitted_additional_nodes` are the exact options submitted to the
selector after hard exclusions; `proposed_additional_nodes` may only request inclusion, and
precedence remains policy-owned. `proposed_strategy` is the untrusted
selector result; `effective_strategy` is the policy outcome. The persisted contract records both,
including abstention or outage reason codes when no valid proposal exists; the schema must allow
`proposed_strategy: null`, `signal: null` and `selector: null` when preflight stops invocation.
`selector_outcome` distinguishes `NOT_INVOKED`, `ANSWERED`, `ABSTAINED`, `TIMED_OUT`,
`INVALID_RESPONSE` and `ERROR`; only `ANSWERED` permits a non-null `proposed_strategy`.
`NOT_INVOKED` requires `selector: null`, `provider_call_id: null`, `signal: null` and
`proposed_strategy: null`. Other unsuccessful outcomes require null proposal/signal and a reason
code; a deterministic local choice may be recorded with `ANSWERED` and null provider call ID.

| Outcome | Effective strategy | Next node | Further rule |
| --- | --- | --- | --- |
| `ROUTED` | eligible machine strategy, never `HUMAN_REVIEW` | one outstanding effective node | null handoff; verified progress revision and dispatch preflight required |
| `ESCALATED` | `HUMAN_REVIEW` | null | non-null handoff reference and authorized scope required; no automatic dispatch |
| `BLOCKED` | null | null | null handoff, typed reason; no dispatch |

An empty candidate set is `BLOCKED` with `NO_ELIGIBLE_STRATEGY`, without selector invocation,
unless policy explicitly requires a valid human handoff. An empty effective path, or one already
verified complete, yields a separate typed `NO_WORK_REQUIRED`/`WORK_COMPLETED` workflow result;
neither is a `ROUTED` decision or a dispatch. Before authenticated tenant/actor identity or a
valid policy is available, return a typed precontract problem response with correlation ID and
safe reason code; never invent tenant, actor, policy or digest values to fill this contract.
`SPECIALIST_REASONING` requires an immutable policy-approved capability ID/version and a current
authorized executor matching that capability at dispatch. If no eligible executor exists,
escalate or block. More than one required specialty needs separately bound steps or escalation.

## 3a. Trusted progress, replay and resume

The progress port returns a tenant-scoped, authenticated record keyed by decision and effective
path digest. Each step has a unique instance ID and node definition version; an accepted result
has a validator/capability version, result reference and digest, bound input/snapshot digest,
authorized producer, validation outcome and immutable audit reference. Pending, running, accepted,
failed and invalidated are distinct states. Only the service may advance a step after validating
the producer and result; it uses compare-and-swap on the monotonic `progress_revision`. A changed
input, expired validator/capability or revoked result invalidates prior acceptance and requires a
new linked decision before further dispatch. Parallel workers cannot select an unverified later
step or both claim the same step. Accepted supplementary nodes count exactly like required nodes.

An `ESCALATED` handoff records case reference, assigned authorized human identity and separate
routing-resume permission, tenant, allowed action and scope, handoff creation and expiry times,
result with evidence reference, and cancellation/timeout state. Resume checks reviewer authority,
current policy and progress, then atomically closes the handoff and records a new decision linked
to its predecessor. Expiry, revocation or failed validation blocks resume. Routing review is not
DA approval; the human cannot mark a validation step accepted without its validator result.

Idempotency uses tenant, actor, request ID, operation and immutable mission revision plus the
bound input digest; conflicting reuse fails. Retention and expiry are policy-set and recorded;
expired keys cannot silently reuse a historical decision. Replaying the same key returns the
original immutable decision for inspection but never reuses it as permission to dispatch. Before
every dispatch attempt (including an outbox restart or retry), verify current actor/workload
authorization, tenant, policy version and content, revocation/stop switch, specialist eligibility,
step claim, input binding and progress revision. A changed condition blocks the attempt and
requires a new linked decision under current policy; the old result is not overwritten. A stale
P1 result under P2 cannot produce a network call even if replay returns `ROUTED` historically.

`signal.probabilities` is optional and must either cover exactly the submitted candidate
strategies with finite values in [0, 1] summing to 1 within a declared tolerance, or be `null`.
Selector confidence is separately optional and must carry documented provider semantics before
use; do not derive it
as `1 - uncertainty` or as the top probability. Until calibrated, probabilities and confidence
are diagnostic evidence only and cannot authorize a cheaper route. Selectors must be version
identified; aliases with mutable behavior cannot support reproducible pilot or production claims.

Supported code values are language-neutral. DE/EN user and audit-display messages use localization
keys; input language and user locale are distinct and an unsupported or unsafe translation cannot
silently change route. The v0.1 JSON Schema must constrain required fields, enums, identifier
lengths, digests, bounds, unknown fields and all nullable/abstention cases.

## 4. Policy and failure rules

- Evaluate hard constraints (risk, legal or regulated domain, data sensitivity, tenant entitlement,
  locality, required specialty, available tools and human-review requirement) and bind the
  required path before probabilistic selection. Provider output cannot relax them or mark a check
  done. `SPECIALIST_REASONING` requires an explicit capability and an eligible specialist;
  otherwise escalate.
- Derive permitted strategies and required nodes from trusted policy and claims. A missing policy,
  ambiguous identity, wrong tenant, incompatible contract or failed integrity check blocks routing.
  A provider failure may use a documented local safe strategy only where policy proves it satisfies
  every required node and hard constraint;
  otherwise route to `HUMAN_REVIEW` or return a typed blocked result.
- Do not invent numeric cutoffs. Record a threshold policy proposal only after blinded labels,
  calibration and false-fast evaluation with a deterministic baseline. A high score never overrides
  a mandatory exclusion. Any downshift after new evidence requires a new versioned route decision.
- Use stable reason codes and append-only `routing.decision` plus `routing.egress-decision` events.
  Bind events to tenant, actor, request, decision ID, manifest, selector outcome/call ID, policy,
  paths, progress revision, strategies, UTC time and correlation ID. Redact secrets, raw prompts
  and personal content. Historical replay returns the same result only; a reused ID with a
  different bound input fails. A unique durable dispatch intent is separately required.
- External selectors require a separate allowlisted request-time egress guard, residency and
  subprocessor evidence, bounded timeout/retry/cost, approved secret provider and no network call
  on preflight or audit failure. The current deployment profile is authoritative. Disable hidden
  SDK retries or prove that each actual transport attempt independently passes the guard and audit;
  pin the approved destination, prohibit unexpected redirects and enforce a total time/cost budget.
- A routing `HUMAN_REVIEW` handoff needs a case reference, authenticated reviewer and scope-bound
  instruction to re-evaluate the route, expiry and atomic resume. It is not a DA approval. Reentry
  creates a new route decision linked to the previous event; the original cannot be overwritten.

## 5. Threats and controls

| Threat | Design control | Verification target |
| --- | --- | --- |
| Prompt injection in task text selects a privileged route | text is data; fixed route set and deterministic policy | adversarial route test |
| Cross-tenant request or replay | verified tenant, tenant-bound hashes and idempotency | two-tenant negative API/E2E test |
| False fast on material work | preflight exclusions, safe fallback and benchmark threshold gate | zero forbidden downshifts; measured false-fast |
| Required check omitted or reordered | ordered policy-bound required path; selector may only add eligible nodes | missing-node, forbidden-addition and order negatives |
| Progress forged, stale or raced | validated step results bound to revision; compare-and-swap claim | parallel-worker, invalidation and resume tests |
| Historical route dispatched after revocation | separate replay from per-attempt authority and policy checks | P1-to-P2 replay and stop-switch tests |
| Provider response cross-bound to a request | server-owned call association and versioned manifest | swapped-response and definition-drift tests |
| Sensitive data sent to provider | minimization, classification and egress guard | zero-call and redaction tests |
| Selector drift or invalid distribution | version pin, strict mapping, shape and calibration checks | contract and regression tests |
| Outage, timeout or lost audit | bounded failure and typed escalation/block | failure-injection E2E |
| SDK retries bypass egress guard | no internal retry; guarded per-attempt loop | revoke between attempts, zero second call |
| Self-approval or DA bypass | route has no assurance or execution authority | negative role and action-binding tests |

## 6. Design verification matrix

`NOT TESTED` means the proposed control has not yet been implemented or verified.

| Requirement | Risk | Control | Evidence | Test or gate | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Input and contract integrity | substituted strategy or dropped check | strict schema, required-path and policy digests | this design only | schema, omission, order and tamper tests | RIF maintainer | NOT TESTED |
| Bound progress and replay | skipped checks or stale dispatch | verified result revisions, linked decisions, guarded outbox | this design only | CAS, P1-to-P2 replay and resume E2E | RIF maintainer | NOT TESTED |
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
2. Approve the precise node taxonomy and ordering, strategy eligibility, specialty identifiers,
   canonical JSON/profile and digest-key retention periods, handoff and audit retention periods,
   and performance/cost budgets. The state and binding rules above are required; implementation
   must prove database-level append-only enforcement for new events before pilot use.
3. Decide which tenant data classes and regions may reach an external provider, based on its
   verified contract, processing, support access and retention terms.
4. Define independent labels, safety-weighted acceptance criteria and responsible human reviewers
   before any threshold or vendor comparison is accepted.
