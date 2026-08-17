# ADR-007: Runtime Contract and execution evidence

**Status:** Proposed for independent review — 2026-08-17

**Issue:** [#10](https://github.com/WernhervonSchrader/Decision-Assurance/issues/10)

**Operating profile:** Development

**Scope:** Architecture and contract mapping only; no runtime implementation is authorized.

## Context

Decision File v0.2 binds an independently approved human decision to one canonical action. It does
not authorize a runtime to execute that action and does not describe what actually happened after an
approval. Treating `APPROVED`, a successful tool response or a confidence score as proof of task
completion would collapse governance, authorization, execution, evidence and organizational
acceptance into one unsafe assertion.

Issue #10 uses research concepts such as an agent trajectory, preventive runtime controls and
evidence-gated completion as design prompts. Research papers and external schemas are informative
inputs only, not normative authority. The project contract, approved ADRs and tested schemas remain
authoritative.

The architecture preserves this separation:

`Assurance Decision != Execution Authorization != Verified Execution Outcome != Human Acceptance`

## Decision drivers

- Do not silently change the published Decision File v0.2 contract.
- Bind every execution record to one tenant, Decision File version, canonical action, approval and
  policy/constraint set.
- Make successful completion deterministic and dependent on checkable mandatory evidence.
- Preserve actor independence and keep human review distinct from technical verification.
- Store only minimized, redacted execution metadata; do not create a general tracing system.
- Fail closed on missing audit, invalid evidence, replay, concurrency conflicts or unavailable
  mandatory dependencies.
- Keep normative codes locale-neutral while supporting equivalent German and English displays.

## Alternatives

### A. Add optional execution fields to Decision File v0.2

This is a small syntactic diff, but v0.2 rejects unknown fields and promises that documentation will
not change the meaning of an existing valid document. Optional execution fields would create two
assurance meanings under one version and could make an old approval appear to grant new authority.

**Rejected:** silent normative change and ambiguous migration semantics.

### B. Publish Decision File v0.3 immediately

Version 0.3 could add a forward reference without mutating v0.2. It would be appropriate if the
binding had to travel inside every Decision File exchange. It would also force every producer and
consumer to migrate before the independent Runtime Contract has been implemented and validated.

**Deferred:** valid future option, but larger than the minimum consistent boundary for Issue #10.

### C. Introduce a separate Runtime Contract v0.1 bound to Decision File v0.2

The Runtime Contract is a separate, versioned aggregate. It references an immutable Decision File by
ID, exact version and full-record digest. It also binds the canonical action, approvals,
policy/constraint set and expected execution evidence. Attempts and verification outcomes live in a
separate append-only ledger.

**Selected:** v0.2 remains unchanged; a later Decision File v0.3 requires a separate ADR, schema and
explicit migration.

## Decision

### 1. Separate lifecycle concepts

| Concept | Normative meaning | What it does not mean |
| --- | --- | --- |
| Planned action | `canonical_action` in Decision File v0.2: effect, target, parameters, tenant, context and reversibility, protected by `canonical_digest`. | Approval, authorization, execution or success. |
| Assurance Decision | Deterministic `decision_outcome` and reasons; the Transition Policy separately controls the resulting Decision File lifecycle transition. | Lifecycle status by itself, permission for runtime I/O or proof that an effect occurred. |
| Execution Authorization | Immutable, short-scope server decision that all bindings and preventive controls passed for one contract and action. | Reusable bearer credential, evidence of execution or organizational approval. |
| Execution Attempt | One uniquely identified invocation under one consumed authorization, with explicit start and terminal state. | Successful effect or evidence verification. |
| Evidence Verification | Deterministic evaluation of artifacts against requirements, digests, freshness, tenant and verifier rules. | Human approval or truth beyond the evidence scope. |
| Completion Decision | Deterministic `PASS` or `FAIL` for one attempt after mandatory evidence checks and required audit writes. | Pilot, production, regulatory or business acceptance. |

An authorization is consumed by at most one attempt. An attempt has only one effective terminal
completion. A later correction is a new superseding event; it never edits history.

### 2. Relationship to Decision File v0.2

Decision File v0.2 remains byte-for-byte and semantically unchanged. Runtime Contract v0.1 is a new
contract family, not a v0.2 extension. It binds:

- `decision_id`, exact `decision_file_version` and a digest of the validated Decision File;
- `canonical_action_digest`;
- ordered unique approval references containing `approval_digest` and nonce digest/reference;
- `constraint_set_digest` over effective policies, constraints and evidence requirements;
- Runtime Contract version/ID and actor-independence policy.

An action-less Decision File cannot create an execution authorization. Existing v0.2 records require
no migration. An authorized service may create a new Runtime Contract from a validated v0.2 snapshot,
but cannot infer missing action or approval authority. A future v0.3 forward reference is a separate
normative decision. No v0.2 record may be relabelled as v0.3.

### 3. Binding invariants

The immutable binding chain is:

```text
tenant_id
  -> decision_id + decision_file_version + decision_file_digest
  -> canonical_action_digest
  -> approval_digest + nonce reference
  -> constraint_set_digest
  -> runtime_contract_id + version + digest
  -> authorization_id
  -> attempt_id
  -> evidence requirement/artifact digests
  -> completion_decision
```

Every record and lookup carries `tenant_id`. Client input never establishes tenant context. The
authenticated server identity supplies it; database RLS is defense in depth.

The constraint-set digest covers the exact ordered, versioned policy and constraint inputs evaluated
at authorization time, including evidence and independence rules. Canonical serialization is
versioned. A changed policy, action, approval, execution context or requirement needs a new Runtime
Contract or authorization. Digest equality proves integrity and binding only; it does not authenticate
an actor or prove an external effect.

### 4. Runtime boundary and non-bypassability claim

The reference ordering is:

```text
authenticate -> resolve tenant -> authorize -> validate bindings
-> persist authorization event -> consume authorization/reserve attempt
-> protected I/O -> observe evidence -> verify -> persist completion
```

Rejected paths must make zero protected-adapter calls. Repository tests can prove reference-adapter
behavior only. They do not prove production non-bypassability. A deployment must separately show
that no alternate credential, network route, tool or operator path reaches the protected target.

### 5. Append-only execution ledger

Decision File events retain governance history. Runtime events use a separate tenant-scoped
append-only ledger so execution data does not mutate the Decision File.

Normative event types are:

- `runtime_contract.bound`;
- `execution.authorization_decided` with `ALLOWED` or `BLOCKED`;
- `execution.attempt_started`;
- `execution.attempt_finished` with observed transport outcome, never inferred completion;
- `execution.evidence_observed`;
- `execution.evidence_availability_changed` for deletion, expiry or loss of reachability;
- `execution.evidence_verified`;
- `execution.completion_decided` with `PASS` or `FAIL`;
- `execution.assertion_superseded` for correction without deletion.

Each event extends the existing v1 envelope with schema version, event ID, timestamp, tenant,
`actor_id`, correlation ID, source component and a strict payload. Runtime payloads add contract,
authorization, attempt and artifact references where applicable, stable reason codes and a payload
digest. `previous_event_hash` links to the canonical hash of the preceding complete event; the first
event uses `null`. The chain is scoped to one tenant and Runtime Contract. Event IDs, monotonic
sequence positions and idempotency keys are unique within tenant/operation scope. Unknown event
versions are rejected under [Event versioning and migration](../EVENT-VERSIONING.md).

Authorization reservation, attempt creation and audit event are atomic. Completion uses
compare-and-swap or an equivalent transaction lock; verification, completion event and terminal state
commit atomically. Identical duplicates replay the committed result. Reuse with a changed digest
fails. Concurrent losers get a conflict or committed replay. A failure before protected I/O rolls
back state and cannot return success. A failure after an adapter may have accepted an effect records
an uncertain terminal transport outcome, forbids blind automatic re-execution and requires
reconciliation by adapter idempotency or independently observed evidence. Audit or mandatory
evidence-store failure blocks authorization/completion.

### 6. Actor independence

Actor identity, role and actor kind remain separate and server-authorized.

| Combination | Rule |
| --- | --- |
| Generator -> Validator | Prohibited by existing Transition Policy. |
| Generator/Requester -> Approver | Prohibited by Decision File v0.2. |
| Validator -> Approver | Prohibited by existing Transition Policy. |
| Generator or Execution Actor -> final verifier | Prohibited for its own mandatory evidence. |
| Agent/Service -> human-review requirement | Prohibited regardless of application role. |
| Deterministic service -> technical verifier | Allowed only if it did not execute or produce the evidence and its version is bound. |
| Approver -> technical verifier | Allowed only if it did not execute/produce evidence and policy requires no different post-execution reviewer. |
| Execution Actor -> evidence producer | Expected for some artifacts, but it cannot finally verify its own mandatory evidence. |
| Auditor -> ledger verification | Tenant-local read/integrity checks only; no mutation or acceptance. |

Material-action profiles default to a verifier distinct from generator, execution actor and evidence
producer. A required post-execution human review is a separate decision, never synthesized from
technical completion. Successful completion does not grant pilot or production acceptance.

### 7. Evidence, privacy and operations

`trajectory_ref` is opaque and bounded, not a raw trajectory. It is tenant-bound through the contract
and ledger, normalized before policy evaluation and accompanied by type, integrity digest,
source/verifier metadata, observation time, availability, data class, retention class and
residency/egress decision.

Decision Assurance does not store prompts, chain-of-thought, tokens, credentials, complete request
bodies or unfiltered screenshots as trajectory evidence. Metadata is minimized and redacted before
durable storage. External content is untrusted data and cannot provide verifier instructions.

Deletion or inaccessibility creates a new availability event. The approved minimum non-sensitive
digest/provenance remains subject to retention and legal hold. If mandatory evidence cannot be
reverified, a new evaluation fails with `EVIDENCE_UNAVAILABLE`; history is not rewritten. Legal hold
is tenant- and scope-bound. Retrieval must pass current residency and egress policy immediately before
access; mismatch makes the artifact unavailable to the gate.

### 8. Multilingual behavior

Contract versions, enums, hashes, IDs and reason codes are locale-neutral and alone affect hashes,
authorization and gates. German and English catalogs render equivalent explanations outside the
normative record. Locale selection/fallback cannot change a digest, tenant, policy or authorization.
Audit stores stable codes; localized display is derived separately. Missing translations use the
documented visible fallback and are tested.

## Contract mapping

| External concept (informative) | Existing DA artifact | Necessary addition | Effect | Open decision | Planned test evidence |
| --- | --- | --- | --- | --- | --- |
| Agent Trajectory Schema | Research attempts/audit | Opaque tenant-bound `trajectory_ref`; no raw trace | DA reference semantics normative; external schema informative | permitted schemes/lifetime | schema, cross-tenant and redaction negatives |
| Evidence Chain | Decision evidence, approvals, deployment evidence | Runtime chain from Decision snapshot to completion | Normative | portable asymmetric signature | tampering, wrong-action and chain tests |
| Evidence-gated completion | Governance/release gates | Attempt-level deterministic mandatory gate | Normative | requirement taxonomy | missing/stale/unavailable evidence |
| Preventive runtime control | Authorization, Transition and egress guards | Authorization/attempt boundary before target I/O | Normative for reference implementation | deployment adapter inventory | zero-I/O spies on rejected paths |
| Trajectory with checkable evidence | Provenance and artifact digests | Typed artifact, verifier, freshness, digest and availability | Metadata normative; external content informative | artifact types by profile | substitution, availability and independence tests |
| Human acceptance | Approval and pilot acceptance | Optional distinct post-execution review | Separate existing authority | deployments requiring review | independent-human and agent-denial E2E |

## Consequences

- Decision File v0.2 remains compatible and unchanged.
- Runtime Contract v0.1 is a separate contract, service and persistence boundary.
- Execution evidence can have a retention lifecycle distinct from governance records.
- Later work needs database tables/RLS, permissions, APIs, localization and E2E paths.
- The extra digest boundary requires canonicalization and migration/version tests.
- Repository evidence is not deployment or organizational authorization.

## Open questions

1. Is the Decision File digest sufficient, or does a portable bundle need an asymmetric signature?
2. Which artifact types are permitted in Development and Controlled Pilot?
3. Which action classes require a distinct post-execution human reviewer?
4. What minimum provenance survives deletion in each retention class?
5. Does interoperability eventually require a Decision File v0.3 forward reference?
6. Which external stores satisfy deletion, legal hold, residency and availability contracts?

## Verification before acceptance

- Review against Issue #10, Decision File v0.2, Transition Policy, OIDC, localization, deployment
  evidence and audit conventions.
- Confirm no artifact or verifier derives authority from its own completion result.
- Confirm technical completion is not organizational acceptance.
- Confirm denied prerequisites stop before protected I/O and success audit.
- Run repository Markdown/link checks and `git diff --check`.
